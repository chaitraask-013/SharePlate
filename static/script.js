
const searchInput = document.getElementById("foodSearch");
const categoryFilter = document.getElementById("foodFilter");
const foodGrid = document.getElementById("foodGrid");
const emptyState = document.getElementById("emptyState");

let donations = [];

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

async function getCurrentUser() {
    try {
        const response = await fetch("/api/me");
        return response.ok ? await response.json() : null;
    } catch {
        return null;
    }
}

async function renderDonations() {
    const searchTerm = searchInput.value.toLowerCase().trim();
    const category = categoryFilter.value;
    const user = await getCurrentUser();

    const filtered = donations.filter(donation => {
        const searchable = [
            donation.food_name,
            donation.category,
            donation.location,
            donation.donor_name,
            donation.description
        ].join(" ").toLowerCase();

        return searchable.includes(searchTerm) &&
            (category === "all" || donation.category === category);
    });

    const categoryLabels = {
        meals: "Prepared meals",
        bakery: "Bakery",
        produce: "Fruits & vegetables",
        other: "Other"
    };

    foodGrid.innerHTML = filtered.map(donation => {
        const imageSection = donation.image_url
            ? `<img src="${escapeHTML(donation.image_url)}"
                    alt="${escapeHTML(donation.food_name)}"
                    class="donation-photo"
                    loading="lazy"
                    onerror="this.style.display='none'; this.nextElementSibling.hidden=false;">
               <div class="food-image-placeholder" hidden>🍲</div>`
            : `<div class="food-image-placeholder">🍲</div>`;

        let buttonHTML = "";

        if (!user) {
            buttonHTML = `
                <button class="card-button claim-button"
                    data-id="${Number(donation.id)}">
                    Log in to request ↗
                </button>`;
        } else if (user.role === "recipient") {
            const status = donation.my_request_status;

            if (status) {
                const labels = {
                    Requested: "Request pending",
                    Approved: "Request approved",
                    Rejected: "Request rejected",
                    Collected: "Already collected"
                };

                buttonHTML = `
                    <p class="request-status-note">
                        Your status: ${escapeHTML(status)}
                    </p>
                    <button class="card-button" disabled>
                        ${escapeHTML(labels[status] || "Already requested")}
                    </button>`;
            } else {
                buttonHTML = `
                    <button class="card-button claim-button"
                        data-id="${Number(donation.id)}">
                        Request donation ↗
                    </button>`;
            }
        } else if (donation.can_manage) {
            buttonHTML = `
                <div class="donation-owner-actions">
                    <button class="card-button edit-donation-button"
                        data-id="${Number(donation.id)}">
                        Edit donation ✎
                    </button>
                    <button class="card-button remove-donation-button"
                        data-id="${Number(donation.id)}">
                        Remove donation ✕
                    </button>
                </div>`;
        } else {
            buttonHTML = `
                <button class="card-button" disabled>
                    Donor account
                </button>`;
        }

        return `
            <article class="food-card">
                <div class="food-image">
                    ${imageSection}
                    <span class="food-tag">
                        ${escapeHTML(categoryLabels[donation.category] || donation.category)}
                    </span>
                </div>

                <div class="food-info">
                    <div class="donor-name">
                        <span class="donor-dot"></span>
                        ${escapeHTML(donation.donor_name)}
                    </div>

                    <h3>${escapeHTML(donation.food_name)}</h3>

                    <p class="food-description">
                        ${escapeHTML(donation.description || "Food available for collection.")}
                    </p>

                    <div class="food-meta">
                        <span>▦ ${escapeHTML(donation.quantity)}</span>
                        <span>⌖ ${escapeHTML(donation.location)}</span>
                    </div>

                    <div class="food-meta">
                        <span>◷ ${escapeHTML(donation.deadline)}</span>
                    </div>

                    ${buttonHTML}
                </div>
            </article>`;
    }).join("");

    emptyState.hidden = filtered.length > 0;
    emptyState.textContent = donations.length
        ? "No matching food found. Try another search."
        : "No donations available yet. Check back soon!";
}

async function loadDonations() {
    foodGrid.innerHTML =
        '<p class="loading-message">Loading donations...</p>';

    try {
        const response = await fetch("/api/donations");
        if (!response.ok) throw new Error("Could not load donations.");

        donations = await response.json();
        await renderDonations();
    } catch {
        foodGrid.innerHTML =
            '<p class="loading-message">Unable to load donations. Please refresh.</p>';
    }
}

searchInput.addEventListener("input", renderDonations);
categoryFilter.addEventListener("change", renderDonations);


// Mobile navigation
const menuToggle = document.getElementById("menuToggle");
const navLinks = document.querySelector(".nav-links");

if (menuToggle && navLinks) {
    menuToggle.addEventListener("click", () => {
        const open = navLinks.classList.toggle("open");
        menuToggle.textContent = open ? "✕" : "☰";
        menuToggle.setAttribute("aria-expanded", String(open));
    });

    navLinks.querySelectorAll("a").forEach(link => {
        link.addEventListener("click", () => {
            navLinks.classList.remove("open");
            menuToggle.textContent = "☰";
            menuToggle.setAttribute("aria-expanded", "false");
        });
    });
}


// Donation form
const donationForm = document.getElementById("donationForm");
const formMessage = document.getElementById("formMessage");
const deadlineInput = document.getElementById("deadline");
const imageInput = document.getElementById("foodImage");

function setMinimumDeadline() {
    if (!deadlineInput) return;

    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    deadlineInput.min = now.toISOString().slice(0, 16);
}

setMinimumDeadline();

if (donationForm) {
    donationForm.addEventListener("submit", async event => {
        event.preventDefault();

        formMessage.textContent = "";
        formMessage.className = "form-message";

        if (new Date(deadlineInput.value) <= new Date()) {
            formMessage.textContent = "Choose a future collection deadline.";
            formMessage.classList.add("error");
            return;
        }

        const image = imageInput?.files?.[0];

        if (image) {
            if (!["image/jpeg", "image/png", "image/webp"].includes(image.type)) {
                formMessage.textContent = "Choose a JPG, PNG or WebP image.";
                formMessage.classList.add("error");
                return;
            }

            if (image.size > 5 * 1024 * 1024) {
                formMessage.textContent = "Image must be smaller than 5 MB.";
                formMessage.classList.add("error");
                return;
            }
        }

        const submitButton = donationForm.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.textContent = "Publishing...";

        try {
            const response = await fetch("/api/donations", {
                method: "POST",
                body: new FormData(donationForm)
            });

            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not publish donation.");

            formMessage.textContent = "Donation published successfully!";
            formMessage.classList.add("success");

            donationForm.reset();
            setMinimumDeadline();
            await loadDonations();
        } catch (error) {
            formMessage.textContent = error.message;
            formMessage.classList.add("error");
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = "Publish donation ↗";
        }
    });
}


// Request, edit and remove actions
foodGrid.addEventListener("click", async event => {
    const requestButton = event.target.closest(".claim-button");
    const removeButton = event.target.closest(".remove-donation-button");
    const editButton = event.target.closest(".edit-donation-button");

    if (requestButton) {
        const user = await getCurrentUser();

        if (!user) {
            window.location.href = "/login";
            return;
        }

        if (user.role !== "recipient") {
            alert("Only recipient accounts can request food.");
            return;
        }

        requestButton.disabled = true;
        requestButton.textContent = "Sending request...";

        try {
            const response = await fetch(
                `/api/donations/${requestButton.dataset.id}/request`,
                { method: "POST" }
            );

            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not send request.");

            alert("Request sent successfully!");
            window.location.href = "/dashboard";
        } catch (error) {
            alert(error.message);
            requestButton.disabled = false;
            requestButton.textContent = "Request donation ↗";
        }

        return;
    }

    if (removeButton) {
        if (!confirm("Remove this donation from the public food list?")) return;

        removeButton.disabled = true;
        removeButton.textContent = "Removing...";

        try {
            const response = await fetch(
                `/api/donations/${removeButton.dataset.id}/remove`,
                { method: "POST" }
            );

            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not remove donation.");

            alert(result.message);
            await loadDonations();
        } catch (error) {
            alert(error.message);
            removeButton.disabled = false;
            removeButton.textContent = "Remove donation ✕";
        }

        return;
    }

    if (editButton) {
        const donation = donations.find(
            item => Number(item.id) === Number(editButton.dataset.id)
        );

        if (!donation) {
            alert("Could not find this donation. Refresh the page.");
            return;
        }

        showEditForm(donation);
    }
});


// Edit form displayed on the page
function showEditForm(donation) {
    const oldForm = document.getElementById("editDonationForm");
    if (oldForm) oldForm.remove();

    const form = document.createElement("form");
    form.id = "editDonationForm";
    form.className = "edit-donation-form";

    form.innerHTML = `
        <h2>Edit donation</h2>
        <p>Update the details below and save your changes.</p>

        <label for="editFoodName">Food name *</label>
        <input id="editFoodName" name="food_name" maxlength="200" required>

        <label for="editCategory">Category *</label>
        <select id="editCategory" name="category" required>
            <option value="meals">Prepared meals</option>
            <option value="bakery">Bakery</option>
            <option value="produce">Fruits & vegetables</option>
            <option value="other">Other</option>
        </select>

        <label for="editQuantity">Quantity *</label>
        <input id="editQuantity" name="quantity" maxlength="1000" required>

        <label for="editLocation">Location *</label>
        <input id="editLocation" name="location" maxlength="1000" required>

        <label for="editDeadline">Collection deadline *</label>
        <input id="editDeadline" name="deadline" type="datetime-local" required>

        <label for="editDescription">Description</label>
        <textarea id="editDescription" name="description" maxlength="1000"></textarea>

        <p class="edit-current-image">
            ${donation.image_url
                ? `Current photo: <a href="${escapeHTML(donation.image_url)}" target="_blank" rel="noopener noreferrer">View photo</a>`
                : "No current photo"}
        </p>

        <label for="editImage">Upload a replacement photo</label>
        <input id="editImage" name="image" type="file"
            accept="image/jpeg,image/png,image/webp">

        <label for="editImageUrl">Or paste a new image link</label>
        <input id="editImageUrl" name="image_url" type="url"
            placeholder="https://example.com/food.jpg">

        <label class="edit-remove-image">
            <input type="checkbox" name="remove_image" value="true">
            Remove the current photo
        </label>

        <p class="edit-form-message" role="status"></p>

        <div class="edit-form-actions">
            <button type="submit" class="primary-button">Save changes</button>
            <button type="button" class="secondary-button edit-cancel">Cancel</button>
        </div>
    `;

    foodGrid.before(form);

    form.querySelector("#editFoodName").value = donation.food_name || "";
    form.querySelector("#editCategory").value = donation.category || "other";
    form.querySelector("#editQuantity").value = donation.quantity || "";
    form.querySelector("#editLocation").value = donation.location || "";
    form.querySelector("#editDeadline").value =
        String(donation.deadline || "").replace(" ", "T").slice(0, 16);
    form.querySelector("#editDescription").value = donation.description || "";

    form.querySelector(".edit-cancel").addEventListener("click", () => {
        form.remove();
    });

    form.querySelector("#editImage").addEventListener("change", () => {
        form.querySelector("#editImageUrl").value = "";
        form.querySelector('[name="remove_image"]').checked = false;
    });

    form.querySelector("#editImageUrl").addEventListener("input", () => {
        if (form.querySelector("#editImageUrl").value) {
            form.querySelector("#editImage").value = "";
            form.querySelector('[name="remove_image"]').checked = false;
        }
    });

    form.querySelector('[name="remove_image"]').addEventListener("change", event => {
        if (event.target.checked) {
            form.querySelector("#editImage").value = "";
            form.querySelector("#editImageUrl").value = "";
        }
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();

        const message = form.querySelector(".edit-form-message");
        const saveButton = form.querySelector('button[type="submit"]');
        const selectedImage = form.querySelector("#editImage").files[0];
        const imageUrl = form.querySelector("#editImageUrl").value.trim();

        message.textContent = "";
        message.className = "edit-form-message";

        if (selectedImage && imageUrl) {
            message.textContent = "Upload a photo OR paste a link, not both.";
            message.classList.add("error");
            return;
        }

        if (selectedImage) {
            if (!["image/jpeg", "image/png", "image/webp"].includes(selectedImage.type)) {
                message.textContent = "Choose a JPG, PNG or WebP image.";
                message.classList.add("error");
                return;
            }

            if (selectedImage.size > 5 * 1024 * 1024) {
                message.textContent = "Image must be smaller than 5 MB.";
                message.classList.add("error");
                return;
            }
        }

        if (new Date(form.querySelector("#editDeadline").value) <= new Date()) {
            message.textContent = "Choose a future collection deadline.";
            message.classList.add("error");
            return;
        }

        saveButton.disabled = true;
        saveButton.textContent = "Saving...";

        try {
            const response = await fetch(
                `/api/donations/${donation.id}/edit`,
                {
                    method: "POST",
                    body: new FormData(form)
                }
            );

            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not edit donation.");

            message.textContent = result.message;
            message.classList.add("success");

            await loadDonations();
            form.remove();
        } catch (error) {
            message.textContent = error.message;
            message.classList.add("error");
            saveButton.disabled = false;
            saveButton.textContent = "Save changes";
        }
    });

    form.scrollIntoView({ behavior: "smooth", block: "start" });
}

loadDonations();
