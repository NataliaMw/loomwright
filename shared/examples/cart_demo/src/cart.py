def total(items, discount_pct):
    subtotal = sum(p for _, p in items)
    return subtotal - discount_pct * subtotal          # bug: treats 10 as 10x, not 10%
