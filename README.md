# WASI Backend API

## Overview
The WASI Backend API is a FastAPI application designed to provide a robust backend for the WASI index calculation and payment verification system. This project includes data pipelines for 16 countries, a payment verification middleware, and a PostgreSQL database for data storage.

## Project Structure
```
wasi-backend-api
├── src
│   ├── main.py                # Entry point of the FastAPI application
│   ├── app.py                 # FastAPI application setup
│   ├── config.py              # Configuration settings
│   ├── database
│   │   ├── models.py          # PostgreSQL database models
│   │   ├── connection.py       # Database connection management
│   │   └── migrations          # Database migration scripts
│   ├── middleware
│   │   ├── x402_payment_verification.py  # Payment verification middleware
│   │   └── __init__.py
│   ├── routes
│   │   ├── __init__.py
│   │   ├── index.py           # Index calculation routes
│   │   └── health.py          # Health check route
│   ├── engines
│   │   ├── __init__.py
│   │   └── index_calculation.py # Index calculation logic
│   ├── pipelines
│   │   ├── __init__.py
│   │   ├── country_data.py     # Country data management
│   │   ├── pipelines
│   │   │   ├── argentina.py
│   │   │   ├── australia.py
│   │   │   ├── brazil.py
│   │   │   ├── canada.py
│   │   │   ├── france.py
│   │   │   ├── germany.py
│   │   │   ├── india.py
│   │   │   ├── japan.py
│   │   │   ├── mexico.py
│   │   │   ├── russia.py
│   │   │   ├── singapore.py
│   │   │   ├── south_africa.py
│   │   │   ├── south_korea.py
│   │   │   ├── uk.py
│   │   │   └── usa.py
│   └── utils
│       ├── __init__.py
│       └── helpers.py         # Utility functions
├── tests
│   ├── __init__.py
│   └── test_api.py            # Unit tests for API endpoints
├── requirements.txt            # Project dependencies
├── .env.example                # Example environment variables
└── README.md                  # Project documentation
```

## Setup Instructions
1. Clone the repository:
   ```
   git clone <repository-url>
   cd wasi-backend-api
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up the environment variables by copying `.env.example` to `.env` and updating the values as needed.

5. Run the application:
   ```
   uvicorn src.main:app --reload
   ```

## Usage
- Access the API at `http://localhost:8000`.
- Use the `/health` endpoint to check if the API is running.
- Utilize the index calculation routes to perform calculations for the specified countries.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for details.