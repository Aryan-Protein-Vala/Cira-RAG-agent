import sys
sys.path.insert(0, "Backend")

from sap import entities

print("=" * 65)
print("  SAP BUSINESS ONE ENTITY & ALIAS REGISTRY")
print("=" * 65)

known = entities.known_entities()
print(f"Total Registered Primary Entities: {len(known)}")
print(f"Total Semantic Table Aliases:     {len(entities.TABLE_ALIASES)}")
print("-" * 65)

print("\nCore Sales & Purchasing Entities:")
for e in known[:12]:
    aliases = ", ".join(e["aliases"][:3])
    print(f"  * Table: {e['table']:6} | {e['description']:30} (Aliases: {aliases})")

print("\nTesting Alias Resolution:")
test_queries = [
    "invoices", 
    "sales orders", 
    "customers", 
    "inventory", 
    "purchase orders", 
    "vendors", 
    "employees",
    "delivery notes",
    "journal entries",
    "credit notes"
]
for q in test_queries:
    table = entities.normalise_table_name(q)
    desc = entities.describe_table_name(table)
    print(f"  Query: \"{q:16}\" -> Physical SAP Table: {table:6} ({desc})")

print("\n" + "=" * 65)
