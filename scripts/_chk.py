import json
d = json.load(open('/tmp/d4_api.json', encoding='utf-8'))
print('error:', d.get('error'))
print('metrics:', d.get('metrics'))
print('warehouses:', [(w['code'], w['name'], w['qty']) for w in d.get('warehouses', [])])
print('details#:', len(d.get('details', [])))
print('expiring#:', len(d.get('expiring', [])))
print('transfers#:', len(d.get('transfers', [])))
for e in d.get('expiring', [])[:4]:
    print(' exp:', e['lot'], e['product'], e['expiration'], e['days'], e['level'])
for d0 in d.get('details', [])[:5]:
    print(' det:', d0['warehouse'], d0['product'], d0['lot'], d0['qty'])
