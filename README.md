
# SharePlate 🍱

SharePlate is a food donation coordination web application that connects food donors with recipients to help reduce food waste.

## Features

- User registration and login
- Separate donor and recipient roles
- Create food donation listings
- Upload food images
- Search and filter available donations
- Edit and remove donation listings
- Request food donations
- Approve or reject recipient requests
- Track food collection status
- Dashboard statistics using SQLite

## Technologies Used

- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript
- Pillow

## How to Run Locally

1. Install Python.
2. Clone or download this repository.
3. Open a terminal in the project directory.
4. Create a virtual environment:

   ```bash
   python -m venv venv
   ```

5. Activate it on Windows PowerShell:

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

6. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

7. Start the application:

   ```bash
   python app.py
   ```

8. Open http://127.0.0.1:5000 in your browser.

## Database

SharePlate uses SQLite for local data storage. The application initializes its database through its Python database setup code.

## Project Purpose

The project aims to make surplus food sharing easier by connecting donors with recipients and tracking donation requests through collection.
