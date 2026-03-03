# Commitments

Code repository for the Commitments software development group project

## How to run the project
1. Clone the repository to your local machine:
   ```bash
   git clone 
   cd Commitments
   ```

2. Open the project folder in your code editor.

3. Make sure your Python version is `3.14.3`:
   - Windows:
     ```bash
     python --version
     ```
   - macOS / Linux:
     ```bash
     python3 --version
     ```

4. Create and activate a virtual environment:
   - Create:
     ```bash
     python -m venv .venv
     ```
   - Activate on Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - Activate on macOS / Linux:
     ```bash
     source .venv/bin/activate
     ```

5. Install the required packages inside the virtual environment:
   ```bash
   python -m pip install -r app/requirements.txt
   ```

6. Set the local Flask environment:
   - macOS / Linux:
     ```bash
     export FLASK_APP=run.py
     ```
   - Windows (PowerShell):
     ```powershell
     $env:FLASK_APP = "run.py"
     ```

7. Run the Flask application:
   If it is your first time running the app:
   ```flask db init```
   
   ```bash
   python -m flask run
   ```

9. Open a browser and go to `http://127.0.0.1:5000` to view the app.

## Updating the database 
1. As a developer modifying the database:
   When developing a feature, if any change is made to the schema of the backend or anything added to it, a migration must be created. This can be done with the command
   ```flask db migrate -m "message about what is being updated here"``` inside the virtual environment. 

2. As a developer pulling in a new feature
   After a new feature is developed and merged into the codebase, if there is a new migration you must update the database in order to ensure it will work properly. THis can be done with the command
   ```flask db upgrade``` inside the virtual environment. 
