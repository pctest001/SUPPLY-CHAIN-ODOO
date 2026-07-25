-- admin login field + password hash (should be pbkdf2_sha512, not plaintext)
SELECT login, left(password,30) AS pw_prefix, length(password) AS pw_len
FROM res_users WHERE login='admin@example.com';

-- login cooldown (must stay at Odoo default: 10 failures / 60s lockout)
SELECT key, value FROM ir_config_parameter
WHERE key IN ('base.login_cooldown_after','base.login_cooldown_duration');

-- demo org: 2 companies
SELECT name FROM res_company WHERE name IN ('华南工厂','华东工厂') ORDER BY name;

-- demo org: 2 extra warehouses
SELECT code, name FROM stock_warehouse WHERE code IN ('HNC2','HDC2') ORDER BY code;

-- AI models registered
SELECT model FROM ir_model
WHERE model IN ('ai.config','ai.chat.session','ai.chat.message','ai.chat.wizard') ORDER BY model;

-- AI / supply-chain menus
SELECT name FROM ir_ui_menu WHERE name ILIKE '%AI%' OR name ILIKE '%供应链%' ORDER BY name;

-- AI access rules count (expect >=4)
SELECT COUNT(*) AS ai_access_rules FROM ir_model_access
WHERE model_id IN (SELECT id FROM ir_model WHERE model IN ('ai.config','ai.chat.session','ai.chat.message','ai.chat.wizard'));
