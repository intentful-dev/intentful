/**
 * Intentful Widget — Chat flutuante para interagir com o agente Intentful
 * Path: intentful/widget/intentful.js
 *
 * Uso:
 *   <script src="http://localhost:8100/widget/intentful.js"></script>
 *   <script>
 *     Intentful.init({ serverUrl: "http://localhost:8100" });
 *   </script>
 */
(function () {
  "use strict";

  var DEFAULT_CONFIG = {
    serverUrl: "http://localhost:8100",
    position: "bottom-right",
    theme: "light",
    language: "pt",
    placeholder: "Escreva o que pretende fazer...",
    title: "Intentful",
    buttonSize: 56,
  };

  var config = {};
  var chatOpen = false;
  var sessionId = null;
  var elements = {};

  // --- Estilos ---
  var STYLES = `
    #intentful-widget * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    #intentful-btn {
      position: fixed;
      z-index: 99999;
      width: {{buttonSize}}px;
      height: {{buttonSize}}px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      font-weight: bold;
      transition: transform 0.2s, box-shadow 0.2s;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    #intentful-btn:hover {
      transform: scale(1.1);
      box-shadow: 0 6px 20px rgba(0,0,0,0.2);
    }
    #intentful-chat {
      position: fixed;
      z-index: 99998;
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 500px;
      max-height: calc(100vh - 100px);
      border-radius: 16px;
      display: none;
      flex-direction: column;
      overflow: hidden;
      box-shadow: 0 8px 32px rgba(0,0,0,0.12);
    }
    #intentful-chat.open {
      display: flex;
    }
    #intentful-header {
      padding: 16px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    #intentful-header h3 {
      font-size: 16px;
      font-weight: 600;
    }
    #intentful-close {
      background: none;
      border: none;
      cursor: pointer;
      font-size: 20px;
      line-height: 1;
      opacity: 0.6;
    }
    #intentful-close:hover { opacity: 1; }
    #intentful-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .intentful-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 14px;
      line-height: 1.5;
      word-wrap: break-word;
    }
    .intentful-msg.user {
      align-self: flex-end;
      border-bottom-right-radius: 4px;
    }
    .intentful-msg.assistant {
      align-self: flex-start;
      border-bottom-left-radius: 4px;
    }
    .intentful-msg.error {
      align-self: flex-start;
      border-bottom-left-radius: 4px;
    }
    #intentful-input-area {
      padding: 12px 16px;
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }
    #intentful-input {
      flex: 1;
      padding: 10px 14px;
      border-radius: 24px;
      border: 1px solid;
      font-size: 14px;
      outline: none;
    }
    #intentful-input:focus {
      border-color: #6366f1;
      box-shadow: 0 0 0 2px rgba(99,102,241,0.2);
    }
    #intentful-send {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      flex-shrink: 0;
    }
    .intentful-typing {
      align-self: flex-start;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 14px;
      opacity: 0.7;
    }

    /* Themes */
    .intentful-light #intentful-btn {
      background: #6366f1;
      color: #fff;
    }
    .intentful-light #intentful-chat {
      background: #fff;
      border: 1px solid #e5e7eb;
    }
    .intentful-light #intentful-header {
      background: #6366f1;
      color: #fff;
    }
    .intentful-light #intentful-close { color: #fff; }
    .intentful-light #intentful-messages { background: #f9fafb; }
    .intentful-light .intentful-msg.user { background: #6366f1; color: #fff; }
    .intentful-light .intentful-msg.assistant { background: #fff; color: #1f2937; border: 1px solid #e5e7eb; }
    .intentful-light .intentful-msg.error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
    .intentful-light #intentful-input { background: #fff; border-color: #d1d5db; color: #1f2937; }
    .intentful-light #intentful-input-area { background: #fff; border-top: 1px solid #e5e7eb; }
    .intentful-light #intentful-send { background: #6366f1; color: #fff; }
    .intentful-light .intentful-typing { background: #fff; color: #6b7280; }

    .intentful-dark #intentful-btn {
      background: #818cf8;
      color: #fff;
    }
    .intentful-dark #intentful-chat {
      background: #1f2937;
      border: 1px solid #374151;
    }
    .intentful-dark #intentful-header {
      background: #111827;
      color: #f9fafb;
    }
    .intentful-dark #intentful-close { color: #f9fafb; }
    .intentful-dark #intentful-messages { background: #1f2937; }
    .intentful-dark .intentful-msg.user { background: #818cf8; color: #fff; }
    .intentful-dark .intentful-msg.assistant { background: #374151; color: #f3f4f6; }
    .intentful-dark .intentful-msg.error { background: #450a0a; color: #fca5a5; border: 1px solid #7f1d1d; }
    .intentful-dark #intentful-input { background: #374151; border-color: #4b5563; color: #f9fafb; }
    .intentful-dark #intentful-input-area { background: #111827; border-top: 1px solid #374151; }
    .intentful-dark #intentful-send { background: #818cf8; color: #fff; }
    .intentful-dark .intentful-typing { background: #374151; color: #9ca3af; }
  `;

  // --- Posicionamento ---
  function getPositionCSS(pos, btnSize) {
    var offset = 24;
    var chatBottom = offset + btnSize + 16;
    switch (pos) {
      case "bottom-left":
        return {
          btn: "bottom:" + offset + "px;left:" + offset + "px;",
          chat: "bottom:" + chatBottom + "px;left:" + offset + "px;",
        };
      case "top-right":
        return {
          btn: "top:" + offset + "px;right:" + offset + "px;",
          chat: "top:" + (offset + btnSize + 16) + "px;right:" + offset + "px;",
        };
      case "top-left":
        return {
          btn: "top:" + offset + "px;left:" + offset + "px;",
          chat: "top:" + (offset + btnSize + 16) + "px;left:" + offset + "px;",
        };
      default: // bottom-right
        return {
          btn: "bottom:" + offset + "px;right:" + offset + "px;",
          chat: "bottom:" + chatBottom + "px;right:" + offset + "px;",
        };
    }
  }

  // --- Mensagens ---
  function addMessage(text, type) {
    var msg = document.createElement("div");
    msg.className = "intentful-msg " + type;
    msg.textContent = text;
    elements.messages.appendChild(msg);
    elements.messages.scrollTop = elements.messages.scrollHeight;
  }

  function showTyping() {
    var el = document.createElement("div");
    el.className = "intentful-typing";
    el.id = "intentful-typing";
    el.textContent = "...";
    elements.messages.appendChild(el);
    elements.messages.scrollTop = elements.messages.scrollHeight;
  }

  function hideTyping() {
    var el = document.getElementById("intentful-typing");
    if (el) el.remove();
  }

  // --- API ---
  function sendPrompt(text) {
    addMessage(text, "user");
    showTyping();

    var body = {
      prompt: text,
      language: config.language,
      mode: sessionId ? "conversational" : "single",
    };
    if (sessionId) {
      body.session_id = sessionId;
      body.mode = "conversational";
    }

    fetch(config.serverUrl + "/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        hideTyping();

        if (data.conversation) {
          // Modo conversacional
          sessionId = data.conversation.session_id;
          if (data.conversation.question) {
            addMessage(data.conversation.question, "assistant");
          }
          if (data.conversation.result) {
            var resultText = typeof data.conversation.result === "string"
              ? data.conversation.result
              : JSON.stringify(data.conversation.result, null, 2);
            addMessage(resultText, "assistant");
            sessionId = null; // Sessao concluida
          }
        } else if (data.success) {
          // Resultado directo
          if (data.confirmation_required) {
            addMessage(data.confirmation_message || "Confirma esta operacao?", "assistant");
          } else if (data.result !== null && data.result !== undefined) {
            var text = typeof data.result === "string"
              ? data.result
              : JSON.stringify(data.result, null, 2);
            addMessage(text, "assistant");
          } else if (data.message) {
            addMessage(data.message, "assistant");
          } else {
            addMessage("Operacao concluida.", "assistant");
          }
        } else {
          addMessage(data.error || "Erro desconhecido.", "error");
          if (data.validation_details && data.validation_details.suggestion) {
            addMessage(data.validation_details.suggestion, "assistant");
          }
        }
      })
      .catch(function (err) {
        hideTyping();
        addMessage("Erro de conexao: " + err.message, "error");
      });
  }

  // --- Init ---
  function init(userConfig) {
    config = {};
    for (var key in DEFAULT_CONFIG) {
      config[key] = userConfig && userConfig[key] !== undefined
        ? userConfig[key]
        : DEFAULT_CONFIG[key];
    }

    // Injectar estilos
    var styleEl = document.createElement("style");
    styleEl.textContent = STYLES.replace(/\{\{buttonSize\}\}/g, config.buttonSize);
    document.head.appendChild(styleEl);

    var pos = getPositionCSS(config.position, config.buttonSize);
    var themeClass = "intentful-" + config.theme;

    // Container
    var widget = document.createElement("div");
    widget.id = "intentful-widget";
    widget.className = themeClass;

    // Botao "i"
    var btn = document.createElement("button");
    btn.id = "intentful-btn";
    btn.setAttribute("style", pos.btn);
    btn.textContent = "i";
    btn.title = "Intentful — descreva o que pretende";
    btn.onclick = function () {
      chatOpen = !chatOpen;
      elements.chat.classList.toggle("open", chatOpen);
      if (chatOpen) elements.input.focus();
    };

    // Chat
    var chat = document.createElement("div");
    chat.id = "intentful-chat";
    chat.setAttribute("style", pos.chat);

    chat.innerHTML =
      '<div id="intentful-header">' +
        '<h3>' + config.title + '</h3>' +
        '<button id="intentful-close">&times;</button>' +
      '</div>' +
      '<div id="intentful-messages"></div>' +
      '<div id="intentful-input-area">' +
        '<input id="intentful-input" type="text" placeholder="' + config.placeholder + '" />' +
        '<button id="intentful-send">&rarr;</button>' +
      '</div>';

    widget.appendChild(btn);
    widget.appendChild(chat);
    document.body.appendChild(widget);

    // Refs
    elements.btn = btn;
    elements.chat = chat;
    elements.messages = chat.querySelector("#intentful-messages");
    elements.input = chat.querySelector("#intentful-input");
    elements.send = chat.querySelector("#intentful-send");
    elements.close = chat.querySelector("#intentful-close");

    // Events
    elements.close.onclick = function () {
      chatOpen = false;
      elements.chat.classList.remove("open");
    };

    elements.send.onclick = function () {
      var text = elements.input.value.trim();
      if (!text) return;
      elements.input.value = "";
      sendPrompt(text);
    };

    elements.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        elements.send.onclick();
      }
    });
  }

  // --- API publica ---
  window.Intentful = {
    init: init,
    open: function () {
      chatOpen = true;
      if (elements.chat) elements.chat.classList.add("open");
    },
    close: function () {
      chatOpen = false;
      if (elements.chat) elements.chat.classList.remove("open");
    },
    resetSession: function () {
      sessionId = null;
      if (elements.messages) elements.messages.innerHTML = "";
    },
  };
})();
