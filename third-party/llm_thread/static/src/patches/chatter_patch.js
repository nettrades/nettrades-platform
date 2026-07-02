/** @odoo-module **/

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { LLMChatContainer } from "@llm_thread/components/llm_chat_container/llm_chat_container";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted, useEffect } from "@odoo/owl";

// Register LLMChatContainer component with Chatter
Object.assign(Chatter.components, { LLMChatContainer });

/**
 * Patch Chatter to add AI Chat functionality
 * Adds AI button to chatter topbar and inline AI chat mode
 */
patch(Chatter.prototype, {
  setup() {
    super.setup();
    this.orm = useService("orm");
    this.notification = useService("notification");

    // Add LLM chat state
    Object.assign(this.state, {
      isChattingWithLLM: false,
      llmThreadId: null,
    });

    // React to AI chat state changes - the "Odoo way" using OWL
    useEffect(
      () => {
        if (this.state.isChattingWithLLM) {
          // AI chat just opened, focus the composer
          this.focusComposerWhenReady();
        }
      },
      () => [this.state.isChattingWithLLM]
    );

    // Check for pending AI chat open from client action
    onMounted(() => {
      this.checkPendingAIChatOpen();
    });
  },

  /**
   * Check for pending AI chat open from client action.
   * This is more reliable than bus notifications which can fail on cloud deployments.
   * Called on component mount.
   */
  async checkPendingAIChatOpen() {
    const llmStore = this.env.services["llm.store"];
    if (!llmStore) {
      return;
    }

    const pending = llmStore.consumePendingOpenInChatter(
      this.props.threadModel,
      this.props.threadId
    );

    if (!pending) {
      return;
    }

    // If AI chat is already open, don't do anything
    if (this.state.isChattingWithLLM) {
      return;
    }

    // Set the thread ID directly (thread already created by backend)
    this.state.llmThreadId = pending.threadId;

    // Set the LLM thread as the active discuss thread
    const llmThread = this.store.Thread.insert({
      model: "llm.thread",
      id: pending.threadId,
    });

    // Initialize discuss if needed and set thread
    if (!this.store.discuss) {
      this.store.discuss = {};
    }
    this.store.discuss.thread = llmThread;

    // Fetch thread data
    await llmThread.fetchData(["messages"]);

    // Open AI chat mode
    this.state.isChattingWithLLM = true;

    // Auto-trigger generation if requested
    if (pending.autoGenerate) {
      await llmStore.startLLMStreaming(pending.threadId, null);
    }
  },

  /**
   * Focus the composer when it's ready
   * Called by useEffect when AI chat state changes to true
   */
  focusComposerWhenReady() {
    // Wait for OWL rendering to complete (Odoo pattern)
    requestAnimationFrame(() => {
      // Step 1: Scroll the chatter into view (form view scroll)
      const chatterEl = this.rootRef?.el;
      if (chatterEl) {
        chatterEl.scrollIntoView({
          behavior: "smooth",
          block: "nearest", // Don't unnecessarily scroll if already visible
        });
      }

      // Step 2: Find and focus the composer (chatter internal scroll)
      const composerSelectors = [
        ".o-mail-Composer-input",
        ".o-llm-composer-area textarea",
      ];
      const composer = composerSelectors
        .map((sel) => document.querySelector(sel))
        .find((el) => el !== null);

      if (composer) {
        // Wait a bit for chatter scroll to settle, then scroll composer
        setTimeout(() => {
          composer.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
          composer.focus();
        }, 300);
      }
    });
  },

  /**
   * Check if current record supports LLM chat
   * Can be extended to support specific models or conditions
   *
   * @returns {Boolean}
   */
  get shouldShowAIButton() {
    return this.props.threadModel && this.props.threadId;
  },

  /**
   * Toggle AI Chat mode - replaces chatter content with LLM chat
   */
  async onAIChatClick() {
    if (!this.shouldShowAIButton) return;

    if (this.state.isChattingWithLLM) {
      // Exit AI chat mode
      this.state.isChattingWithLLM = false;
      this.state.llmThreadId = null;

      // Clear discuss thread
      if (this.store.discuss) {
        this.store.discuss.thread = undefined;
      }
    } else {
      // Enter AI chat mode - find or create thread
      try {
        const threadId = await this.ensureLLMThread();
        if (threadId) {
          // Set the LLM thread as the active discuss thread
          const llmThread = this.store.Thread.insert({
            model: "llm.thread",
            id: threadId,
          });

          // Initialize discuss if needed and set thread
          if (!this.store.discuss) {
            this.store.discuss = {};
          }
          this.store.discuss.thread = llmThread;

          // Fetch thread data
          await llmThread.fetchData(["messages"]);

          this.state.isChattingWithLLM = true;
          this.state.llmThreadId = threadId;
        }
      } catch (error) {
        console.error("Failed to start AI chat:", error);
        this.notification.add(error.message || "Failed to start AI chat", {
          type: "danger",
        });
      }
    }
  },

  /**
   * Find existing LLM thread for current record or create new one
   *
   * @returns {Promise<Number|null>} Thread ID
   */
  async ensureLLMThread() {
    // Search for existing thread linked to this record
    const existingThreads = await this.orm.searchRead(
      "llm.thread",
      [
        ["model", "=", this.props.threadModel],
        ["res_id", "=", this.props.threadId],
      ],
      ["id"],
      { limit: 1 }
    );

    if (existingThreads.length > 0) {
      return existingThreads[0].id;
    }

    // Try to find default chat model
    let modelId = null;
    let providerId = null;

    const defaultModels = await this.orm.searchRead(
      "llm.model",
      [
        ["model_use", "in", ["chat", "multimodal"]],
        ["default", "=", true],
        ["active", "=", true],
      ],
      ["id", "provider_id"],
      { limit: 1 }
    );

    if (defaultModels.length > 0) {
      modelId = defaultModels[0].id;
      providerId = defaultModels[0].provider_id[0];
    } else {
      // Fallback: Get first provider and its first chat model
      const providers = await this.orm.searchRead(
        "llm.provider",
        [["active", "=", true]],
        ["id"],
        { limit: 1 }
      );

      if (providers.length === 0) {
        throw new Error(
          "No active LLM provider found. Please configure a provider first."
        );
      }

      providerId = providers[0].id;

      const models = await this.orm.searchRead(
        "llm.model",
        [
          ["provider_id", "=", providerId],
          ["model_use", "in", ["chat", "multimodal"]],
          ["active", "=", true],
        ],
        ["id"],
        { limit: 1 }
      );

      if (models.length === 0) {
        throw new Error(
          "No active chat model found. Please configure a model first."
        );
      }

      modelId = models[0].id;
    }

    // Create new thread with provider and model - name will be auto-generated by backend
    const threadIds = await this.orm.create("llm.thread", [
      {
        model: this.props.threadModel,
        res_id: this.props.threadId,
        provider_id: providerId,
        model_id: modelId,
      },
    ]);

    // Orm.create returns array of IDs, extract first one
    return Array.isArray(threadIds) ? threadIds[0] : threadIds;
  },
});
