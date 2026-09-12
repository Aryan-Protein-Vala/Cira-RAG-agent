import json

new_questions = [
    # Complex Joins
    {"id": 21, "bucket": "complex_joins", "question": "Show all sales orders along with their corresponding customer names and item details.", "expected_tables": ["ORDR", "OCRD", "RDR1"]},
    {"id": 22, "bucket": "complex_joins", "question": "List the purchase orders, the vendor names, and the warehouse they are delivered to.", "expected_tables": ["OPOR", "OCRD", "POR1", "OWHS"]},
    {"id": 23, "bucket": "complex_joins", "question": "What items have been sold to customer 'C20000' and who was the sales employee?", "expected_tables": ["ORDR", "RDR1", "OHEM", "OITM"]},
    {"id": 24, "bucket": "complex_joins", "question": "Find all invoices that have items belonging to the 'Printers' item group.", "expected_tables": ["OINV", "INV1", "OITM", "OITB"]},
    {"id": 25, "bucket": "complex_joins", "question": "Show the total quantity of 'A00001' ordered by 'Earthshaker Corporation'.", "expected_tables": ["ORDR", "RDR1", "OCRD"]},
    
    # Aggregates & Grouping
    {"id": 26, "bucket": "aggregates", "question": "What is the total sales amount for each sales employee?", "expected_tables": ["OINV", "OHEM", "OSLP"]},
    {"id": 27, "bucket": "aggregates", "question": "Count the number of active items in each item group.", "expected_tables": ["OITM", "OITB"]},
    {"id": 28, "bucket": "aggregates", "question": "Find the average order value per customer.", "expected_tables": ["ORDR", "OCRD"]},
    {"id": 29, "bucket": "aggregates", "question": "What is the maximum discount given on any invoice?", "expected_tables": ["OINV"]},
    {"id": 30, "bucket": "aggregates", "question": "Calculate the total inventory value by warehouse.", "expected_tables": ["OITW", "OITM", "OWHS"]},
    
    # Date Filtering & Time Series
    {"id": 31, "bucket": "time_series", "question": "How many purchase orders were created in Q1 2023?", "expected_tables": ["OPOR"]},
    {"id": 32, "bucket": "time_series", "question": "Show the monthly revenue trend for the last year.", "expected_tables": ["OINV"]},
    {"id": 33, "bucket": "time_series", "question": "Which customers placed orders yesterday?", "expected_tables": ["ORDR", "OCRD"]},
    {"id": 34, "bucket": "time_series", "question": "List all deliveries made in October.", "expected_tables": ["ODLN"]},
    {"id": 35, "bucket": "time_series", "question": "What is the year-to-date total for accounts payable?", "expected_tables": ["OPCH"]},
    
    # Edge Cases & Ambiguity
    {"id": 36, "bucket": "edge_cases", "question": "Who is the contact person for customer 'Maxi-Teq'?", "expected_tables": ["OCPR", "OCRD"]},
    {"id": 37, "bucket": "edge_cases", "question": "Are there any orders without a designated sales employee?", "expected_tables": ["ORDR"]},
    {"id": 38, "bucket": "edge_cases", "question": "Show items with stock levels below their minimum threshold.", "expected_tables": ["OITM"]},
    {"id": 39, "bucket": "edge_cases", "question": "Find invoices where the document total does not match the sum of line totals.", "expected_tables": ["OINV", "INV1"]},
    {"id": 40, "bucket": "edge_cases", "question": "List vendors who have not supplied any goods in the past 6 months.", "expected_tables": ["OCRD", "OPCH"]},
    
    # Master Data
    {"id": 41, "bucket": "master_data", "question": "List all tax codes and their rates.", "expected_tables": ["OVTG"]},
    {"id": 42, "bucket": "master_data", "question": "What are the payment terms for customer 'C20000'?", "expected_tables": ["OCRD", "OCTG"]},
    {"id": 43, "bucket": "master_data", "question": "Show all active currencies.", "expected_tables": ["OCRN"]},
    {"id": 44, "bucket": "master_data", "question": "List all warehouses located in 'New York'.", "expected_tables": ["OWHS"]},
    {"id": 45, "bucket": "master_data", "question": "Who is the manager of the 'Sales' department?", "expected_tables": ["OHEM", "OUDP"]},
    
    # Inventory Valuation
    {"id": 46, "bucket": "inventory", "question": "What is the valuation method for item 'A00001'?", "expected_tables": ["OITM"]},
    {"id": 47, "bucket": "inventory", "question": "Show the moving average price for items in the 'Servers' group.", "expected_tables": ["OITM", "OITW"]},
    {"id": 48, "bucket": "inventory", "question": "List all goods receipts for item 'A00002'.", "expected_tables": ["OPDN", "PDN1"]},
    {"id": 49, "bucket": "inventory", "question": "What is the total committed stock across all warehouses?", "expected_tables": ["OITW"]},
    {"id": 50, "bucket": "inventory", "question": "Find items with zero on-hand quantity but positive on-order quantity.", "expected_tables": ["OITM", "OITW"]},
    
    # Financials
    {"id": 51, "bucket": "financials", "question": "Show the chart of accounts.", "expected_tables": ["OACT"]},
    {"id": 52, "bucket": "financials", "question": "What is the current balance of the 'Cash in Bank' account?", "expected_tables": ["OACT"]},
    {"id": 53, "bucket": "financials", "question": "List all journal entries posted today.", "expected_tables": ["OJDT", "JDT1"]},
    {"id": 54, "bucket": "financials", "question": "Show the total debits and credits for project 'P01'.", "expected_tables": ["JDT1"]},
    {"id": 55, "bucket": "financials", "question": "Find all incoming payments that are unreconciled.", "expected_tables": ["ORCT", "OINV"]},
    
    # HR & Payroll
    {"id": 56, "bucket": "hr", "question": "List all active employees and their job titles.", "expected_tables": ["OHEM"]},
    {"id": 57, "bucket": "hr", "question": "Who are the subordinates of employee 'E001'?", "expected_tables": ["OHEM"]},
    
    # Service & Support
    {"id": 58, "bucket": "service", "question": "Show all open service calls assigned to technician 'T01'.", "expected_tables": ["OSCL", "OHEM"]},
    {"id": 59, "bucket": "service", "question": "What is the average resolution time for service calls this month?", "expected_tables": ["OSCL"]},
    {"id": 60, "bucket": "service", "question": "List all customer equipment cards linked to item 'A00001'.", "expected_tables": ["OINS"]}
]

with open('tests/accuracy/suite_sandbox.jsonl', 'a') as f:
    for q in new_questions:
        f.write(json.dumps(q) + '\n')
