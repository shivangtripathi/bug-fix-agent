
def add(a, b):
    return a + b

def sub(a, b):
    return a - b

def mul(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Inputs must be numbers.")
    return a * b

def div(a, b):
    return a / b