import { registry } from "@web/core/registry";
import { AiChatSystray } from "./ai_chat_panel/ai_chat_panel";

// G7：在顶栏右侧注册 AI 聊天 systray 按钮
registry.category("systray").add("sc_ai_chat", AiChatSystray, { sequence: 100 });
