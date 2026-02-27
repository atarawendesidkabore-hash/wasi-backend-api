def calculate_percentage(part, whole):
    if whole == 0:
        return 0
    return (part / whole) * 100

def format_currency(amount):
    return "${:,.2f}".format(amount)

def validate_input(data, expected_type):
    if not isinstance(data, expected_type):
        raise ValueError(f"Expected data of type {expected_type}, got {type(data)}")

def log_error(message):
    # Placeholder for logging errors
    print(f"ERROR: {message}")

def parse_date(date_string):
    from datetime import datetime
    try:
        return datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        log_error(f"Invalid date format: {date_string}")
        return None

def generate_response(data, status_code=200):
    return {
        "status": status_code,
        "data": data
    }