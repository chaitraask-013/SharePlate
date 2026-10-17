
import os
import re
import secrets
import uuid
import ipaddress
import sqlite3
from pathlib import Path
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageOps, UnidentifiedImageError

from database import init_db, get_db_connection


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = Path("/tmp/shareplate_uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config.update(
    UPLOAD_FOLDER=str(UPLOAD_FOLDER),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_HTTPS") == "1",
)

ALLOWED_IMAGE_FORMATS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}

init_db()


# ---------------- AUTHENTICATION ----------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please log in first."}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"error": "Please log in first."}), 401
            if session.get("role") != role:
                return jsonify({"error": "You do not have permission."}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------------- IMAGE HELPERS ----------------

def save_food_image(file):
    if not file or not file.filename:
        return None

    try:
        file.stream.seek(0)

        with Image.open(file.stream) as image:
            image_format = image.format
            if image_format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("Use a JPG, PNG or WebP image.")
            image.verify()

        file.stream.seek(0)

        with Image.open(file.stream) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1600, 1600))

            filename = f"{uuid.uuid4().hex}{ALLOWED_IMAGE_FORMATS[image_format]}"
            destination = UPLOAD_FOLDER / filename

            if image_format == "JPEG":
                image.convert("RGB").save(
                    destination, format="JPEG", quality=85
                )
            elif image_format == "PNG":
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                image.save(destination, format="PNG", optimize=True)
            else:
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                image.save(destination, format="WEBP", quality=85)

        return filename

    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("Invalid image. Upload a valid JPG, PNG or WebP file.")


def validate_image_url(value):
    if not value:
        return None
    if len(value) > 2000:
        raise ValueError("Image link is too long.")

    parsed = urlparse(value)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Enter a valid public HTTPS image link.")

    hostname = parsed.hostname.lower()

    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise ValueError("Use a public image link.")

    try:
        address = ipaddress.ip_address(hostname)
        if not address.is_global:
            raise ValueError("Use a public image link.")
    except ValueError as error:
        if str(error) == "Use a public image link.":
            raise

    return value


@app.errorhandler(413)
def file_too_large(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "Image is too large. Maximum size is 5 MB."
        }), 413
    return "Upload too large. Maximum size is 5 MB.", 413


# ---------------- HOMEPAGE ----------------

@app.route("/")
def home():
    return render_template(
        "index.html",
        logged_in="user_id" in session,
        user_role=session.get("role")
    )


# ---------------- REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        if not name or len(name) > 100:
            flash("Enter a valid name.", "error")
            return render_template("register.html")

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
            flash("Enter a valid email address.", "error")
            return render_template("register.html")

        if len(password) < 8 or len(password) > 128:
            flash("Password must be 8–128 characters long.", "error")
            return render_template("register.html")

        if role not in ("donor", "recipient"):
            flash("Choose a valid account type.", "error")
            return render_template("register.html")

        conn = get_db_connection()
        try:
            cursor = conn.execute("""
                INSERT INTO users (name, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            """, (name, email, generate_password_hash(password), role))
            conn.commit()
            user_id = cursor.lastrowid

        except Exception as exc:
            conn.rollback()
            if "UNIQUE constraint failed" in str(exc):
                flash("An account with this email already exists.", "error")
            else:
                app.logger.exception("Registration failed")
                flash("Could not create the account. Please try again.", "error")
            return render_template("register.html")
        finally:
            conn.close()

        session.clear()
        session["user_id"] = user_id
        session["name"] = name
        session["role"] = role

        flash("Welcome to SharePlate!", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]

        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))


@app.route("/api/me")
@login_required
def current_user():
    return jsonify({
        "id": session["user_id"],
        "name": session["name"],
        "role": session["role"]
    })


# ---------------- GET DONATIONS ----------------

@app.route("/api/donations", methods=["GET"])
def get_donations():
    conn = get_db_connection()

    recipient_id = (
        session["user_id"]
        if session.get("role") == "recipient"
        else -1
    )

    rows = conn.execute("""
        SELECT
            d.id, d.food_name, d.category, d.quantity,
            d.donor_name, d.location, d.deadline,
            d.description, d.status, d.image_path, d.donor_id,
            r.status AS my_request_status
        FROM donations d
        LEFT JOIN donation_requests r
            ON r.donation_id = d.id
            AND r.recipient_id = ?
        WHERE d.status = 'Available'
        ORDER BY d.created_at DESC
    """, (recipient_id,)).fetchall()

    conn.close()
    results = []

    for row in rows:
        donation = dict(row)

        donation["can_manage"] = (
            session.get("role") == "donor"
            and donation["donor_id"] == session.get("user_id")
        )

        image_path = donation.get("image_path")

        if image_path and image_path.startswith("https://"):
            donation["image_url"] = image_path
        elif image_path:
            donation["image_url"] = url_for(
                "static", filename=f"uploads/{image_path}"
            )
        else:
            donation["image_url"] = None

        results.append(donation)

    return jsonify(results)


# ---------------- ADD DONATION ----------------

@app.route("/api/donations", methods=["POST"])
@login_required
@role_required("donor")
def add_donation():
    data = request.form

    fields = ["food_name", "category", "quantity", "location", "deadline"]

    for field in fields:
        value = data.get(field, "").strip()
        if not value:
            return jsonify({
                "error": f"{field.replace('_', ' ').title()} is required."
            }), 400
        if len(value) > 1000:
            return jsonify({"error": "A field is too long."}), 400

    description = data.get("description", "").strip()
    if len(description) > 1000:
        return jsonify({
            "error": "Description must be 1000 characters or fewer."
        }), 400

    category = data.get("category", "").strip()
    if category not in ("meals", "bakery", "produce", "other"):
        return jsonify({"error": "Choose a valid category."}), 400

    try:
        deadline = datetime.fromisoformat(data["deadline"])
        if deadline <= datetime.now():
            return jsonify({
                "error": "Choose a future collection deadline."
            }), 400
    except ValueError:
        return jsonify({"error": "Invalid deadline."}), 400

    image_file = request.files.get("image")
    image_url = data.get("image_url", "").strip()

    if image_file and image_file.filename and image_url:
        return jsonify({
            "error": "Upload a photo OR paste an image link, not both."
        }), 400

    try:
        image_filename = (
            validate_image_url(image_url)
            if image_url else save_food_image(image_file)
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO donations (
                food_name, category, quantity, donor_name,
                location, deadline, description, donor_id, image_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["food_name"].strip(),
            category,
            data["quantity"].strip(),
            session["name"],
            data["location"].strip(),
            deadline.isoformat(timespec="minutes"),
            description,
            session["user_id"],
            image_filename
        ))
        conn.commit()
        donation_id = cursor.lastrowid

    except Exception:
        conn.rollback()
        if image_filename and not image_url:
            (UPLOAD_FOLDER / image_filename).unlink(missing_ok=True)
        app.logger.exception("Could not save donation")
        return jsonify({
            "error": "Could not publish the donation. Please try again."
        }), 500
    finally:
        conn.close()

    return jsonify({
        "message": "Donation published successfully!",
        "id": donation_id
    }), 201


# ---------------- EDIT A DONATION ----------------

@app.route("/api/donations/<int:donation_id>/edit", methods=["POST"])
@login_required
@role_required("donor")
def edit_donation(donation_id):
    data = request.form
    conn = get_db_connection()
    new_image_filename = None

    try:
        donation = conn.execute("""
            SELECT id, donor_id, status, image_path
            FROM donations
            WHERE id = ?
        """, (donation_id,)).fetchone()

        if not donation:
            return jsonify({"error": "Donation not found."}), 404

        if donation["donor_id"] != session["user_id"]:
            return jsonify({
                "error": "You can only edit your own donations."
            }), 403

        if donation["status"] != "Available":
            return jsonify({
                "error": "Only available donations can be edited."
            }), 409

        food_name = data.get("food_name", "").strip()
        category = data.get("category", "").strip()
        quantity = data.get("quantity", "").strip()
        location = data.get("location", "").strip()
        deadline_text = data.get("deadline", "").strip()
        description = data.get("description", "").strip()

        if not all([
            food_name, category, quantity, location, deadline_text
        ]):
            return jsonify({
                "error": "Fill in all required fields."
            }), 400

        if any(len(value) > 1000 for value in [
            food_name, quantity, location, deadline_text
        ]):
            return jsonify({"error": "A field is too long."}), 400

        if len(food_name) > 200:
            return jsonify({
                "error": "Food name must be 200 characters or fewer."
            }), 400

        if len(description) > 1000:
            return jsonify({
                "error": "Description must be 1000 characters or fewer."
            }), 400

        if category not in ("meals", "bakery", "produce", "other"):
            return jsonify({"error": "Choose a valid category."}), 400

        try:
            deadline = datetime.fromisoformat(deadline_text)
            if deadline <= datetime.now():
                return jsonify({
                    "error": "Choose a future collection deadline."
                }), 400
        except ValueError:
            return jsonify({"error": "Invalid deadline."}), 400

        image_file = request.files.get("image")
        image_url = data.get("image_url", "").strip()
        remove_image = data.get("remove_image") == "true"

        if image_file and image_file.filename and image_url:
            return jsonify({
                "error": "Upload a photo OR paste an image link, not both."
            }), 400

        if remove_image and (
            (image_file and image_file.filename) or image_url
        ):
            return jsonify({
                "error": "Choose a new image or remove the old one, not both."
            }), 400

        current_image = donation["image_path"]

        if remove_image:
            new_image_filename = None

        elif image_url:
            new_image_filename = validate_image_url(image_url)

        elif image_file and image_file.filename:
            new_image_filename = save_food_image(image_file)

        else:
            # Keep the existing image when no replacement is supplied.
            new_image_filename = current_image

        conn.execute("""
            UPDATE donations
            SET food_name = ?,
                category = ?,
                quantity = ?,
                location = ?,
                deadline = ?,
                description = ?,
                image_path = ?
            WHERE id = ? AND donor_id = ? AND status = 'Available'
        """, (
            food_name,
            category,
            quantity,
            location,
            deadline.isoformat(timespec="minutes"),
            description,
            new_image_filename,
            donation_id,
            session["user_id"]
        ))

        conn.commit()

        # Delete the previous uploaded file only after the DB update succeeds.
        if (
            current_image
            and current_image != new_image_filename
            and not current_image.startswith("https://")
        ):
            old_file = UPLOAD_FOLDER / current_image
            old_file.unlink(missing_ok=True)

        return jsonify({
            "message": "Donation updated successfully!"
        })

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    except Exception:
        conn.rollback()

        # Clean up a newly uploaded file if saving the update failed.
        if (
            new_image_filename
            and new_image_filename != donation["image_path"]
            and not new_image_filename.startswith("https://")
        ):
            (UPLOAD_FOLDER / new_image_filename).unlink(missing_ok=True)

        app.logger.exception("Could not edit donation")
        return jsonify({
            "error": "Could not update the donation. Please try again."
        }), 500

    finally:
        conn.close()



# ---------------- REMOVE DONATION ----------------

@app.route("/api/donations/<int:donation_id>/remove", methods=["POST"])
@login_required
@role_required("donor")
def remove_donation(donation_id):
    conn = get_db_connection()

    try:
        donation = conn.execute("""
            SELECT id, donor_id, status
            FROM donations
            WHERE id = ?
        """, (donation_id,)).fetchone()

        if not donation:
            return jsonify({"error": "Donation not found."}), 404

        if donation["donor_id"] != session["user_id"]:
            return jsonify({
                "error": "You can only remove your own donations."
            }), 403

        if donation["status"] != "Available":
            return jsonify({
                "error": "Only available donations can be removed."
            }), 409

        conn.execute("""
            UPDATE donations
            SET status = 'Removed'
            WHERE id = ?
        """, (donation_id,))
        conn.commit()

        return jsonify({
            "message": "Donation removed from the available food list."
        })

    except Exception:
        conn.rollback()
        app.logger.exception("Could not remove donation")
        return jsonify({
            "error": "Could not remove the donation. Please try again."
        }), 500
    finally:
        conn.close()


# ---------------- REQUEST A DONATION ----------------

@app.route("/api/donations/<int:donation_id>/request", methods=["POST"])
@login_required
@role_required("recipient")
def request_donation(donation_id):
    conn = get_db_connection()

    try:
        donation = conn.execute("""
            SELECT id, donor_id, status
            FROM donations
            WHERE id = ?
        """, (donation_id,)).fetchone()

        if not donation or donation["status"] != "Available":
            return jsonify({
                "error": "This donation is no longer available."
            }), 404

        if donation["donor_id"] == session["user_id"]:
            return jsonify({
                "error": "You cannot request your own donation."
            }), 403

        conn.execute("""
            INSERT INTO donation_requests (donation_id, recipient_id)
            VALUES (?, ?)
        """, (donation_id, session["user_id"]))
        conn.commit()

        return jsonify({"message": "Donation request sent successfully."}), 201

    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({
            "error": "You have already requested this donation."
        }), 409
    except Exception:
        conn.rollback()
        app.logger.exception("Could not create donation request")
        return jsonify({
            "error": "Could not send the request. Please try again."
        }), 500
    finally:
        conn.close()


# ---------------- APPROVE OR REJECT REQUEST ----------------

@app.route("/api/requests/<int:request_id>/decision", methods=["POST"])
@login_required
@role_required("donor")
def decide_request(request_id):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")

    if decision not in ("Approved", "Rejected"):
        return jsonify({"error": "Choose Approved or Rejected."}), 400

    conn = get_db_connection()

    try:
        item = conn.execute("""
            SELECT r.id AS request_id, r.status AS request_status,
                   r.donation_id, d.donor_id, d.status AS donation_status
            FROM donation_requests r
            JOIN donations d ON d.id = r.donation_id
            WHERE r.id = ?
        """, (request_id,)).fetchone()

        if not item:
            return jsonify({"error": "Request not found."}), 404
        if item["donor_id"] != session["user_id"]:
            return jsonify({"error": "You can only manage your own donations."}), 403
        if item["request_status"] != "Requested":
            return jsonify({"error": "This request has already been processed."}), 409
        if item["donation_status"] != "Available":
            return jsonify({"error": "This donation is no longer available."}), 409

        if decision == "Approved":
            conn.execute("""
                UPDATE donation_requests
                SET status = 'Rejected'
                WHERE donation_id = ? AND id != ? AND status = 'Requested'
            """, (item["donation_id"], request_id))

            conn.execute("""
                UPDATE donations SET status = 'Reserved'
                WHERE id = ? AND status = 'Available'
            """, (item["donation_id"],))

        conn.execute("""
            UPDATE donation_requests SET status = ?
            WHERE id = ? AND status = 'Requested'
        """, (decision, request_id))
        conn.commit()

        return jsonify({
            "message": f"Request {decision.lower()} successfully.",
            "status": decision
        })

    except Exception:
        conn.rollback()
        app.logger.exception("Could not process donation request")
        return jsonify({
            "error": "Could not process the request. Please try again."
        }), 500
    finally:
        conn.close()


# ---------------- MARK COLLECTED ----------------

@app.route("/api/requests/<int:request_id>/collected", methods=["POST"])
@login_required
@role_required("donor")
def mark_collected(request_id):
    conn = get_db_connection()

    try:
        item = conn.execute("""
            SELECT r.id, r.status, r.donation_id, d.donor_id
            FROM donation_requests r
            JOIN donations d ON d.id = r.donation_id
            WHERE r.id = ?
        """, (request_id,)).fetchone()

        if not item:
            return jsonify({"error": "Request not found."}), 404
        if item["donor_id"] != session["user_id"]:
            return jsonify({"error": "You can only update your own donations."}), 403
        if item["status"] != "Approved":
            return jsonify({
                "error": "Only approved requests can be marked collected."
            }), 409

        conn.execute("""
            UPDATE donation_requests SET status = 'Collected'
            WHERE id = ?
        """, (request_id,))
        conn.execute("""
            UPDATE donations SET status = 'Collected'
            WHERE id = ?
        """, (item["donation_id"],))
        conn.commit()

        return jsonify({"message": "Donation marked as collected."})

    except Exception:
        conn.rollback()
        app.logger.exception("Could not mark donation collected")
        return jsonify({
            "error": "Could not update the collection status."
        }), 500
    finally:
        conn.close()


# ---------------- DASHBOARD ----------------


# ---------------- DASHBOARD WITH REAL STATISTICS ----------------

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()

    user_id = session["user_id"]
    role = session["role"]

    if role == "donor":

        # All donations belonging to this donor
        donations = conn.execute("""
            SELECT *
            FROM donations
            WHERE donor_id = ?
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()

        # Incoming requests for this donor's donations
        requests = conn.execute("""
            SELECT
                r.id AS request_id,
                r.status AS request_status,
                r.created_at AS request_created_at,
                u.name AS recipient_name,
                u.email AS recipient_email,
                d.id AS donation_id,
                d.food_name,
                d.quantity,
                d.location,
                d.status AS donation_status
            FROM donation_requests r
            JOIN users u ON u.id = r.recipient_id
            JOIN donations d ON d.id = r.donation_id
            WHERE d.donor_id = ?
            ORDER BY r.created_at DESC
        """, (user_id,)).fetchall()

        # Actual donation statistics
        donation_stats = conn.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Available'
                    THEN 1 ELSE 0 END) AS available,
                SUM(CASE WHEN status = 'Reserved'
                    THEN 1 ELSE 0 END) AS reserved,
                SUM(CASE WHEN status = 'Collected'
                    THEN 1 ELSE 0 END) AS collected,
                SUM(CASE WHEN status = 'Removed'
                    THEN 1 ELSE 0 END) AS removed
            FROM donations
            WHERE donor_id = ?
        """, (user_id,)).fetchone()

        # Actual request statistics for this donor's donations
        request_stats = conn.execute("""
            SELECT
                SUM(CASE WHEN r.status = 'Requested'
                    THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN r.status = 'Approved'
                    THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN r.status = 'Rejected'
                    THEN 1 ELSE 0 END) AS rejected,
                SUM(CASE WHEN r.status = 'Collected'
                    THEN 1 ELSE 0 END) AS collected
            FROM donation_requests r
            JOIN donations d ON d.id = r.donation_id
            WHERE d.donor_id = ?
        """, (user_id,)).fetchone()

        stats = {
            "total_donations": donation_stats["total"] or 0,
            "available_donations": donation_stats["available"] or 0,
            "reserved_donations": donation_stats["reserved"] or 0,
            "removed_donations": donation_stats["removed"] or 0,
            "pending_requests": request_stats["pending"] or 0,
            "approved_requests": request_stats["approved"] or 0,
            "rejected_requests": request_stats["rejected"] or 0,
            "collected_donations": donation_stats["collected"] or 0
        }

    else:

        # Available donations recipients can browse
        donations = conn.execute("""
            SELECT *
            FROM donations
            WHERE status = 'Available'
            ORDER BY created_at DESC
        """).fetchall()

        # Requests created by this recipient
        requests = conn.execute("""
            SELECT
                r.id AS request_id,
                r.status AS request_status,
                r.created_at AS request_created_at,
                d.id AS donation_id,
                d.food_name,
                d.quantity,
                d.location,
                d.status AS donation_status,
                u.name AS donor_name
            FROM donation_requests r
            JOIN donations d ON d.id = r.donation_id
            LEFT JOIN users u ON u.id = d.donor_id
            WHERE r.recipient_id = ?
            ORDER BY r.created_at DESC
        """, (user_id,)).fetchall()

        # Actual request statistics for this recipient
        request_stats = conn.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Requested'
                    THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'Approved'
                    THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN status = 'Rejected'
                    THEN 1 ELSE 0 END) AS rejected,
                SUM(CASE WHEN status = 'Collected'
                    THEN 1 ELSE 0 END) AS collected
            FROM donation_requests
            WHERE recipient_id = ?
        """, (user_id,)).fetchone()

        stats = {
            "total_requests": request_stats["total"] or 0,
            "pending_requests": request_stats["pending"] or 0,
            "approved_requests": request_stats["approved"] or 0,
            "rejected_requests": request_stats["rejected"] or 0,
            "collected_donations": request_stats["collected"] or 0,
            "available_donations": conn.execute("""
                SELECT COUNT(*) AS total
                FROM donations
                WHERE status = 'Available'
            """).fetchone()["total"]
        }

    conn.close()

    return render_template(
        "dashboard.html",
        donations=donations,
        requests=requests,
        stats=stats,
        role=role,
        name=session["name"]
    )
if __name__ == "__main__":
    app.run(debug=True)