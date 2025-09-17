import yaml
import csv
import logging

logger = logging.getLogger(__name__)

def load_yaml(file_path):
    try:
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading YAML file {file_path}: {e}")
        raise

def load_csv(file_path):
    try:
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            # Convert boolean strings to booleans
            data = []
            for row in reader:
                for key, value in row.items():
                    if isinstance(value, str) and value.lower() == 'true':
                        row[key] = True
                    elif isinstance(value, str) and value.lower() == 'false':
                        row[key] = False
                data.append(row)
            return data
    except Exception as e:
        logger.error(f"Error loading CSV file {file_path}: {e}")
        raise

class Config:
    # Load general config
    _config = load_yaml('config.yaml')
    SCRAPE_INTERVAL = _config.get('scrape_interval_minutes', 5)
    TIMEOUT = _config.get('timeout_seconds', 60)

    # Load loyalty program configuration
    LOYALTY_NAMES = _config.get('loyalty_program', {}).get('names', ['rewards 2 go'])

    # Load commanders
    COMMANDERS = load_csv('commanders.csv')

    # Load credentials
    _credentials = load_yaml('credentials.yaml')
    USERNAME = _credentials['credentials']['username']
    PASSWORD = _credentials['credentials']['password']
