def total(items, discount_pct):
    subtotal = sum(p for _, p in items)
    return subtotal - (discount_pct / 100) * subtotal   # discount_pct is a percentage
