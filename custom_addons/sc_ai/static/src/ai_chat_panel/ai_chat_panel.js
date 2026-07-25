import { Component } from "@odoo/owl";
import { useState, useRef, onPatched } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Portal } from "@web/core/portal/portal";

/**
 * G7 · OWL 侧边聊天面板
 * 顶栏 systray 按钮 + 右侧滑出面板（Portal 到 body，避免 navbar 层级/containing-block 影响）。
 * 复用后端 ai.chat.session 的 ask()：只读、继承权限、白名单、降级均天然生效。
 */
export class AiChatSystray extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            open: false,
            loading: false,
            messages: [],
            error: null,
        });
        this.sessionId = null;
        this.inputRef = useRef("input");
        this.messagesRef = useRef("messages");
        onPatched(() => this._scrollBottom());
    }

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open && this.sessionId === null) {
            this._loadSession();
        }
    }

    async _loadSession() {
        try {
            const res = await this.rpc("/web/dataset/call_kw", {
                model: "ai.chat.session",
                method: "get_or_create_session",
                args: [],
                kwargs: {},
            });
            this.sessionId = res.id;
            this.state.messages = res.messages || [];
        } catch (e) {
            this.state.error = "加载对话失败，请刷新后重试";
        }
    }

    async newChat() {
        try {
            const res = await this.rpc("/web/dataset/call_kw", {
                model: "ai.chat.session",
                method: "new_session",
                args: [],
                kwargs: {},
            });
            this.sessionId = res.id;
            this.state.messages = [];
            this.state.error = null;
        } catch (e) {
            this.state.error = "新建对话失败，请刷新后重试";
        }
    }

    async send() {
        const input = this.inputRef.el;
        const text = (input.value || "").trim();
        if (!text || this.state.loading) {
            return;
        }
        input.value = "";
        this.state.loading = true;
        this.state.error = null;
        this.state.messages.push({ role: "user", content: text });
        try {
            const res = await this.rpc("/web/dataset/call_kw", {
                model: "ai.chat.session",
                method: "chat",
                args: [this.sessionId, text],
                kwargs: {},
            });
            this.sessionId = res.id || this.sessionId;
            this.state.messages = res.messages || [];
        } catch (e) {
            this.state.error = "AI 请求失败，请稍后重试";
            this.state.messages.push({
                role: "assistant",
                content: "（请求失败，请稍后重试）",
            });
        } finally {
            this.state.loading = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    _scrollBottom() {
        const el = this.messagesRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }
}

AiChatSystray.template = "sc_ai.AiChatSystray";
AiChatSystray.components = { Portal };
