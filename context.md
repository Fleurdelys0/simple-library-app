PROJECT: Python Library Management System

OVERALL OBJECTIVE: To build a comprehensive library management application by progressing through three main development stages: a command-line interface (CLI) built with OOP, integration with an external API for data enrichment, and the creation of a web API using FastAPI to serve the application's logic. 

PHASE 1: OOP Console Application

Goal: Develop a modular and manageable console application using Object-Oriented Programming (OOP) principles. 

Tasks:

Implement Book Class:

Create a 

Book class to represent a single book. 

It must have 

title, author, and isbn as attributes. 

Override the 

__str__ method to return a human-readable string representation (e.g., "Ulysses by James Joyce (ISBN: 978-0199535675)"). 

Implement Library Class:

Create a 

Library class to manage all library operations. 

The 

__init__ method should initialize a list to store books and accept a filename for data persistence (e.g., library.json). 

Implement the following methods: 

add_book(book) , 

remove_book(isbn) , 

list_books() , 

find_book(isbn) , 



save_books() , and 



load_books().



Develop Main Application Loop (main.py):

Create a main loop that presents a menu to the user with the following options: Add Book, Remove Book, List Books, Find Book, and Exit. 

Call the appropriate 

Library methods based on user input. 

Ensure data persistence: call 

load_books() on startup and save_books() after any modification (add/remove). 



Implement Tests:

Install 

pytest. 

Write Python scripts to test the core functionalities of the 

Library class (add, remove, list, persistence). 

Deliverables (Minimum Acceptance Criteria):

The program runs from the command line without errors. 

Add, remove, and list functions work as expected. 

Book data is persisted in 

library.json between sessions. 

The code is structured using 

Book and Library classes. 

Pytest scripts for unit tests are present and pass. 

PHASE 2: External API Integration

Goal: Enhance the application by fetching book data from the external Open Library Books API to make it more intelligent and user-friendly. 

Tasks:

Setup Dependencies:

Install the 

httpx library using pip. 


Add 

httpx to the requirements.txt file. 

Update add_book Functionality:

Modify the user prompt to only ask for the book's ISBN number. 

Refactor the 

Library.add_book method to accept an isbn string as its parameter. 

Implement API Call Logic:

Within the 

add_book method, make a GET request to https://openlibrary.org/isbn/{isbn}.json. 

Parse the resulting JSON to extract the 

title and authors. 

Create a new 

Book object with the fetched data and add it to the library. 

Implement Error Handling:

Use 

try-except blocks to ensure the application does not crash if the API request fails (e.g., no internet) or if the ISBN is not found (API returns a 404 status). 

Display a meaningful message like "Book not found." to the user in case of failure. 

Implement Tests:

Write new 

pytest scripts to test the updated add_book functionality, covering both successful and unsuccessful API calls. 


Deliverables (Minimum Acceptance Criteria):

The application successfully fetches the book title and author from the Open Library API when a valid ISBN is provided. 

The program handles invalid or non-existent ISBNs gracefully without crashing. 

The 

requirements.txt file is updated to include httpx. 

Pytest scripts for the new API functionality are present and pass. 

PHASE 3: Creating Your Own API with FastAPI

Goal: Transform the application logic into a web service, making the data accessible via a web API. 

Tasks:

Setup Dependencies and File Structure:

Install 

fastapi and uvicorn. 

Update 

requirements.txt with these new dependencies. 

Create a new file named 

api.py. 

Define Pydantic Data Models:

Use Pydantic's 

BaseModel to define the data structures for the Book object (API responses) and the ISBN object (for POST requests). This improves data validation and documentation. 


Create API Endpoints:

In 

api.py, use the Library class logic to power the API endpoints. 


GET /books: Returns a JSON list of all books in the library. 


POST /books: Accepts a JSON body with an ISBN (e.g., {"isbn": "978-0321765723"}). It uses the logic from Phase 2 to fetch data from Open Library, adds the book, and returns the result. 




DELETE /books/{isbn}: Deletes the book with the specified ISBN. 

Test the API:

Start the server using the command 

uvicorn api:app --reload. 

Access the interactive API documentation at 

/docs in your browser and test all endpoints. 

Write separate 

pytest scripts to test the API endpoints. 

Deliverables (Minimum Acceptance Criteria):

The API server starts without any errors. 

The interactive documentation at 

/docs is accessible and functional. 

The 

GET /books, POST /books, and DELETE /books/{isbn} endpoints all work as expected. 

All project dependencies are correctly listed in 

requirements.txt. 

PHASE 4: Finalization and Documentation
Goal: Prepare the project for submission by creating comprehensive documentation and performing a final review.

Tasks:


Complete the README.md File: 


Add a Project Title and a brief Description. 

Add a "Setup" section explaining how to clone the repo and install dependencies (

pip install -r requirements.txt). 

Add a "Usage" section explaining how to run the CLI (

python main.py) and the API server (uvicorn api:app --reload). 

Add an "API Documentation" section listing the endpoints, their functions, and an example body for the POST request. 

Final Review:

Ensure the GitHub repository is set to public. 

Verify that all test scenarios pass. 

(Bonus) Review git commit history to ensure messages are descriptive and reflect the project's stages. 

Deliverables:

A complete and detailed README.md file.

A fully functional project meeting all criteria across all three stages.

A clean, public GitHub repository ready for evaluation. 