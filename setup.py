from setuptools import setup, find_packages

setup(
    name="disaster_relief_backend",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.111.0",
        "uvicorn[standard]>=0.30.0",
        "pydantic>=2.7.0",
        "pandas>=2.2.0",
        "numpy>=1.26.0",
        "pulp>=2.8.0",
        "requests>=2.31.0",
        "ortools>=9.10.4067",
        "python-multipart"
    ],
)
