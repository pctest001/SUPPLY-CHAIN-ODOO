-- ============================================================
-- 供应链系统（Odoo 18）常用查询 — supplychain 库
-- 在 DBeaver 中打开，选中某段按 Ctrl+Enter 执行即可
-- 说明：Odoo 18 中 product_template.name 为普通文本（中文直存）；
--       is_process_mfg 为自定义字段，落在 product_template 上。
-- ============================================================

-- 1) 实时库存（按 仓库 / 物料 / 批次），只看非零库存
SELECT l.complete_name              AS 仓库,
       p.default_code               AS 物料编码,
       pt.name                      AS 物料名称,
       lot.name                     AS 批次,
       q.quantity                   AS 数量
FROM stock_quant q
JOIN product_product p       ON p.id = q.product_id
JOIN product_template pt     ON pt.id = p.product_tmpl_id
JOIN stock_location l        ON l.id = q.location_id
LEFT JOIN stock_lot lot      ON lot.id = q.lot_id
WHERE q.quantity <> 0
ORDER BY l.complete_name, p.default_code, lot.name
LIMIT 200;

-- 2) 各仓库库存汇总（按物料合计，含批次维度）
SELECT l.complete_name              AS 仓库,
       p.default_code               AS 物料编码,
       pt.name                      AS 物料名称,
       COUNT(DISTINCT lot.id)       AS 批次数,
       SUM(q.quantity)              AS 总数量
FROM stock_quant q
JOIN product_product p   ON p.id = q.product_id
JOIN product_template pt ON pt.id = p.product_tmpl_id
JOIN stock_location l    ON l.id = q.location_id
LEFT JOIN stock_lot lot  ON lot.id = q.lot_id
WHERE q.quantity <> 0
GROUP BY l.complete_name, p.default_code, pt.name
ORDER BY l.complete_name, 总数量 DESC
LIMIT 200;

-- 3) 临期批次预警（N 天内过期，当前设为 60 天）
SELECT lot.name                     AS 批次,
       pt.name                      AS 物料名称,
       lot.expiration_date          AS 效期,
       (lot.expiration_date - CURRENT_DATE) AS 剩余天数,
       COALESCE(q.quantity, 0)      AS 库存数量,
       c.name                       AS 公司
FROM stock_lot lot
JOIN product_product p   ON p.id = lot.product_id
JOIN product_template pt ON pt.id = p.product_tmpl_id
LEFT JOIN stock_quant q  ON q.lot_id = lot.id AND q.quantity > 0
LEFT JOIN res_company c  ON c.id = lot.company_id
WHERE lot.expiration_date IS NOT NULL
  AND lot.expiration_date <= CURRENT_DATE + INTERVAL '60 days'
ORDER BY lot.expiration_date;

-- 4) 跨仓调拨作业（内部调拨 internal）
SELECT pick.name                    AS 调拨单,
       ptype.name                   AS 调拨类型,
       pick.state                   AS 状态,
       sl.complete_name             AS 来源仓,
       sld.complete_name            AS 目的仓,
       pick.create_date             AS 创建时间
FROM stock_picking pick
JOIN stock_picking_type ptype ON ptype.id = pick.picking_type_id
JOIN stock_location sl       ON sl.id = pick.location_id
JOIN stock_location sld      ON sld.id = pick.location_dest_id
WHERE ptype.code = 'internal'
ORDER BY pick.create_date DESC;

-- 5) 流程制造物料（按批次追踪 + 效期）
SELECT p.default_code               AS 物料编码,
       pt.name                      AS 物料名称,
       pt.is_process_mfg            AS 是否流程制造,
       pt.tracking                  AS 追踪方式,
       pt.use_expiration_date       AS 启用效期
FROM product_template pt
JOIN product_product p ON p.product_tmpl_id = pt.id
WHERE pt.is_process_mfg = TRUE
ORDER BY pt.name;

-- 6) 入库 / 出库作业（按状态）
SELECT pick.name                    AS 单号,
       ptype.name                   AS 作业类型,
       ptype.code                   AS 方向,
       pick.state                   AS 状态,
       sl.complete_name             AS 来源,
       sld.complete_name            AS 目的
FROM stock_picking pick
JOIN stock_picking_type ptype ON ptype.id = pick.picking_type_id
JOIN stock_location sl       ON sl.id = pick.location_id
JOIN stock_location sld      ON sld.id = pick.location_dest_id
WHERE ptype.code IN ('incoming', 'outgoing')
ORDER BY pick.create_date DESC
LIMIT 100;

-- 7) 公司 / 仓库清单
SELECT c.name                       AS 公司,
       w.name                       AS 仓库,
       w.code                       AS 编码,
       sl.complete_name             AS 库存库位
FROM stock_warehouse w
JOIN res_company c ON c.id = w.company_id
JOIN stock_location sl ON sl.id = w.lot_stock_id
ORDER BY c.name, w.code;
