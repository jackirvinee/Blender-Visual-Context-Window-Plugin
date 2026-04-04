/**
 * Claude Context Window Progress Bar
 *
 * Injected into the Claude desktop app (Electron renderer process).
 * Intercepts streaming API responses to extract token usage data and
 * renders a thin progress bar at the top of the chat window showing
 * how full the context window is.
 *
 * Architecture:
 *   1. Monkey-patches window.fetch to intercept SSE completion streams
 *   2. Parses SSE events for usage data (input_tokens, output_tokens, model)
 *   3. Renders/updates a progress bar DOM element
 *   4. Persists state per conversation in localStorage
 */

(function () {
  "use strict";

  // ── Model context limits ───────────────────────────────────────────
  const MODEL_LIMITS = {
    "claude-opus-4": 200000,
    "claude-sonnet-4": 200000,
    "claude-haiku-3": 200000,
    default: 200000,
  };

  function getModelLimit(modelId) {
    if (!modelId) return MODEL_LIMITS.default;
    for (const key of Object.keys(MODEL_LIMITS)) {
      if (key !== "default" && modelId.startsWith(key)) {
        return MODEL_LIMITS[key];
      }
    }
    return MODEL_LIMITS.default;
  }

  // ── State ──────────────────────────────────────────────────────────
  const STORAGE_KEY = "claude_context_bar_state";
  let currentState = {
    conversationId: null,
    inputTokens: 0,
    outputTokens: 0,
    model: null,
  };

  function getConversationId() {
    const match = window.location.pathname.match(
      /\/chat\/([a-f0-9-]+)/
    );
    return match ? match[1] : null;
  }

  function saveState() {
    try {
      const allState = JSON.parse(
        localStorage.getItem(STORAGE_KEY) || "{}"
      );
      if (currentState.conversationId) {
        allState[currentState.conversationId] = {
          inputTokens: currentState.inputTokens,
          outputTokens: currentState.outputTokens,
          model: currentState.model,
          timestamp: Date.now(),
        };
      }
      // Prune entries older than 7 days
      const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
      for (const id of Object.keys(allState)) {
        if (allState[id].timestamp < cutoff) {
          delete allState[id];
        }
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(allState));
    } catch (e) {
      // Never break the app
    }
  }

  function loadState(conversationId) {
    try {
      const allState = JSON.parse(
        localStorage.getItem(STORAGE_KEY) || "{}"
      );
      const saved = allState[conversationId];
      if (saved) {
        currentState.inputTokens = saved.inputTokens || 0;
        currentState.outputTokens = saved.outputTokens || 0;
        currentState.model = saved.model || null;
      } else {
        currentState.inputTokens = 0;
        currentState.outputTokens = 0;
        currentState.model = null;
      }
      currentState.conversationId = conversationId;
    } catch (e) {
      // Never break the app
    }
  }

  // ── Progress bar DOM ───────────────────────────────────────────────
  const BAR_WRAPPER_ID = "claude-context-bar-wrapper";
  const BAR_FILL_ID = "claude-context-bar-fill";
  const BAR_TOOLTIP_ID = "claude-context-bar-tooltip";

  function getColor(pct) {
    if (pct <= 50) return "#22c55e";
    if (pct <= 75) return "#eab308";
    if (pct <= 90) return "#f97316";
    return "#ef4444";
  }

  function formatTokens(n) {
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
    return String(n);
  }

  function ensureBarExists() {
    if (document.getElementById(BAR_WRAPPER_ID)) return;

    const wrapper = document.createElement("div");
    wrapper.id = BAR_WRAPPER_ID;

    const fill = document.createElement("div");
    fill.id = BAR_FILL_ID;
    wrapper.appendChild(fill);

    const tooltip = document.createElement("div");
    tooltip.id = BAR_TOOLTIP_ID;
    wrapper.appendChild(tooltip);

    // Find the best place to inject — top of the main content area
    const target = findChatContainer();
    if (target) {
      target.insertBefore(wrapper, target.firstChild);
    } else {
      // Fallback: prepend to body
      document.body.prepend(wrapper);
    }
  }

  function findChatContainer() {
    // Try multiple selectors in order of likelihood
    const selectors = [
      "main",
      '[role="main"]',
      "#__next > div > div",
      ".flex-1.overflow-hidden",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return document.body;
  }

  function updateBar() {
    ensureBarExists();

    const limit = getModelLimit(currentState.model);
    const used = currentState.inputTokens + currentState.outputTokens;
    const pct = Math.min(100, (used / limit) * 100);
    const color = getColor(pct);

    const fill = document.getElementById(BAR_FILL_ID);
    if (fill) {
      fill.style.width = pct + "%";
      fill.style.backgroundColor = color;

      // Pulse animation when >85%
      if (pct > 85) {
        fill.classList.add("context-bar-pulse");
      } else {
        fill.classList.remove("context-bar-pulse");
      }
    }

    const tooltip = document.getElementById(BAR_TOOLTIP_ID);
    if (tooltip) {
      const modelName = currentState.model
        ? currentState.model.replace(/-\d{8}$/, "")
        : "unknown model";
      tooltip.textContent =
        formatTokens(used) +
        " / " +
        formatTokens(limit) +
        " tokens (" +
        pct.toFixed(1) +
        "%) \u00b7 " +
        modelName;
    }

    // Update wrapper border color hint
    const wrapper = document.getElementById(BAR_WRAPPER_ID);
    if (wrapper) {
      wrapper.setAttribute("data-usage-level",
        pct > 90 ? "critical" :
        pct > 75 ? "high" :
        pct > 50 ? "medium" : "low"
      );
    }
  }

  // ── SSE stream parser ──────────────────────────────────────────────
  function isCompletionEndpoint(url) {
    if (!url) return false;
    return (
      /\/completion/.test(url) ||
      /\/chat_conversations\/[^/]+\/completion/.test(url)
    );
  }

  function parseSSEEvent(eventText) {
    // SSE format: lines starting with "data: " followed by JSON
    const lines = eventText.split("\n");
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const jsonStr = line.slice(6).trim();
      if (!jsonStr || jsonStr === "[DONE]") continue;

      try {
        const data = JSON.parse(jsonStr);
        handleSSEData(data);
      } catch (e) {
        // Ignore parse errors — some data lines may not be JSON
      }
    }
  }

  function handleSSEData(data) {
    // message_start contains model and initial usage (input_tokens)
    if (data.type === "message_start" && data.message) {
      if (data.message.model) {
        currentState.model = data.message.model;
      }
      if (data.message.usage) {
        currentState.inputTokens =
          data.message.usage.input_tokens || currentState.inputTokens;
        // Reset output tokens for this new message
        currentState.outputTokens = 0;
      }
      updateBar();
    }

    // message_delta contains final output token count
    if (data.type === "message_delta" && data.usage) {
      currentState.outputTokens =
        data.usage.output_tokens || currentState.outputTokens;
      updateBar();
    }

    // message_stop — save final state
    if (data.type === "message_stop") {
      saveState();
      updateBar();
    }
  }

  async function processSSEStream(body) {
    if (!body) return;
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Split on double newlines (SSE event boundary)
        const events = buffer.split("\n\n");
        // Keep the last (possibly incomplete) chunk in the buffer
        buffer = events.pop() || "";

        for (const event of events) {
          if (event.trim()) {
            parseSSEEvent(event);
          }
        }
      }

      // Process any remaining buffered data
      if (buffer.trim()) {
        parseSSEEvent(buffer);
      }
    } catch (e) {
      // Stream read error — don't break the app
    }
  }

  // ── Fetch interceptor ─────────────────────────────────────────────
  const originalFetch = window.fetch;

  window.fetch = async function (...args) {
    let response;
    try {
      response = await originalFetch.apply(this, args);
    } catch (e) {
      throw e; // Re-throw — never swallow the app's fetch errors
    }

    try {
      const url =
        typeof args[0] === "string"
          ? args[0]
          : args[0] instanceof Request
            ? args[0].url
            : args[0]?.url;

      if (url && isCompletionEndpoint(url)) {
        // Update conversation ID from current URL
        const convId = getConversationId();
        if (convId && convId !== currentState.conversationId) {
          loadState(convId);
        }

        // Clone the response so we can read the stream without
        // consuming the one the app needs
        const clone = response.clone();
        processSSEStream(clone.body).catch(function () {
          // Silently ignore stream processing errors
        });
      }
    } catch (e) {
      // Never interfere with the original response
    }

    return response;
  };

  // ── SPA navigation detection ───────────────────────────────────────
  function onNavigate() {
    const convId = getConversationId();
    if (convId !== currentState.conversationId) {
      if (currentState.conversationId) {
        saveState();
      }
      if (convId) {
        loadState(convId);
      } else {
        // New chat — reset
        currentState.conversationId = null;
        currentState.inputTokens = 0;
        currentState.outputTokens = 0;
        currentState.model = null;
      }
      updateBar();
    }
  }

  // Override history methods to detect SPA navigation
  const originalPushState = history.pushState;
  history.pushState = function () {
    originalPushState.apply(this, arguments);
    onNavigate();
  };

  const originalReplaceState = history.replaceState;
  history.replaceState = function () {
    originalReplaceState.apply(this, arguments);
    onNavigate();
  };

  window.addEventListener("popstate", onNavigate);

  // ── DOM resilience ─────────────────────────────────────────────────
  // Re-inject the bar if the DOM changes and our element gets removed
  const observer = new MutationObserver(function () {
    if (!document.getElementById(BAR_WRAPPER_ID)) {
      updateBar();
    }
  });

  // ── Initialization ─────────────────────────────────────────────────
  function init() {
    const convId = getConversationId();
    if (convId) {
      loadState(convId);
    }

    // Inject the bar
    updateBar();

    // Start observing DOM changes
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // Wait for DOM to be ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
