# Disaster Relief Backend

A backend system for managing disaster relief operations, including resource allocation, asset tracking, and zone management.

## Features

- **Asset Management**: Track and manage relief assets and resources
- **Zone Management**: Define and manage disaster-affected zones
- **Optimization Services**: Efficient resource allocation and routing
- **RESTful API**: Easy integration with frontend applications

## Project Structure

```
disaster_relief_backend/
├── database/
│   ├── assets.json      # Asset definitions and inventory
│   ├── depots.json      # Depot locations and information
│   └── zones.json       # Zone definitions and status
├── services/
│   ├── event_handler.py # Handles disaster events and triggers
│   ├── optimizer.py     # Optimization algorithms for resource allocation
│   └── rationals.py     # Utility functions and helpers
├── tests/               # Test files
├── utils/
│   ├── data_loader.py   # Data loading utilities
│   └── distance_matrix.py # Distance calculations
├── main.py              # Main application entry point
├── models.py            # Data models and schemas
├── requirements.txt     # Python dependencies
└── wsgi.py             # WSGI application entry point
```

## Prerequisites

- Python 3.8+
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd disaster_relief_backend
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. Update the database files in the `database/` directory with your specific configurations:
   - `assets.json`: Define your relief assets and resources
   - `depots.json`: Configure depot locations and capacities
   - `zones.json`: Set up disaster-affected zones

## Running the Application

Start the development server:
```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`

## API Documentation

Once the server is running, you can access the interactive API documentation at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Running Tests

To run the test suite:
```bash
pytest tests/
```


