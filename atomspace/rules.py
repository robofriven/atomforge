# rules.py
"""
Inference / rewrite rules live here.

Examples:
- transitivity: IsA(a,b) and IsA(b,c) => IsA(a,c)
- propagation: Sees(a,x) => Believes(a, Exists(x))
- narrative rules: Claims(minstrel, p) => Believes(audience, p) (lol)
"""
