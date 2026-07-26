"""PRD 业务规则（业务数值断言的唯一权威来源）。

提炼自：
- 验收清单.md  §2 C1「PR→PO：状态机 + 一键转原生 PO」
- 作品说明.md  §4 E「供应商交期确认单(待确认/已确认/已驳回)」、§6 C1 PR→PO

红线（技术方案 v2.1 P0#3）：本文件的 expect_state / expect_field 是业务数值期望的
唯一权威，修改须同步 PRD 文档；严禁直接抄代码 state 字符串而不经 PRD 核对。
生成器（prdgen.py）消费本文件，不读取代码逻辑反推期望。

字段说明：
- id        用例稳定 ID（需求-用例双向追溯用）
- source    PRD 溯源（哪份文档哪条）
- desc      业务期望的自然语言描述
- model     目标模型
- mode      执行策略：submit / genpo / ack_confirm
- expect_state  期望达到的业务状态值（来自 PRD 规定的状态机）
- expect_field  额外需非空的联动字段（如生成 PO 后 po_ids）
"""
PRD_RULES = [
    {
        "id": "PR-SUBMIT",
        "source": "验收清单.md §2 C1 / 作品说明.md §6 C1 PR→PO",
        "desc": "草稿态采购申请添加明细后提交，状态推进为『已提交』",
        "model": "sc.purchase.request",
        "mode": "submit",
        "expect_state": "confirmed",  # PRD『已提交』在模型中的取值
    },
    {
        "id": "PR-GENPO",
        "source": "验收清单.md §2 C1『一键转原生 PO』",
        "desc": "已提交采购申请选定供应商后生成 PO，状态推进为『完成』且联动原生采购订单",
        "model": "sc.purchase.request",
        "mode": "genpo",
        "expect_state": "done",       # PRD『完成/生成PO后』在模型中的取值
        "expect_field": "po_ids",
    },
    {
        "id": "ACK-CONFIRM",
        "source": "作品说明.md §4 E『供应商交期确认单(待确认/已确认/已驳回)』",
        "desc": "待确认交期确认单填写交期后确认，状态推进为『已确认』",
        "model": "sc.supplier.ack",
        "mode": "ack_confirm",
        "expect_state": "confirmed",   # PRD『已确认』在模型中的取值
    },
]
