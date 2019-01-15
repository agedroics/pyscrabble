def int_to_byte(n: int) -> bytes:
    return n.to_bytes(1, byteorder='big')