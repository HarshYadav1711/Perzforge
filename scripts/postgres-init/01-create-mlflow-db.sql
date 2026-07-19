-- Created on first postgres volume init only (story B4).
-- If postgres-data already exists, create manually:
--   CREATE DATABASE mlflow; GRANT ALL PRIVILEGES ON DATABASE mlflow TO perzforge;
CREATE DATABASE mlflow;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO perzforge;
