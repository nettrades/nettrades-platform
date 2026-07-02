/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";
import { router } from "@web/core/browser/router";

/**
 * Patch Thread model to properly handle llm.thread URLs
 *
 * TODO: Fix mobile routing for llm.thread
 * Issue: On mobile (ui.isSmall), clicking an llm.thread opens the form view instead of the chat UI
 * Root cause: llmStore.selectThread() calls thread.setAsDiscussThread(), which doesn't know
 *             how to handle llm.thread on mobile. It falls back to opening the form view.
 *
 * Attempted solutions that didn't work:
 * - Overriding thread.open() → caused infinite recursion
 * - Overriding thread.openChatWindow() → never called (different code path)
 * - Overriding thread.setAsDiscussThread() → navigation throttling (infinite loop)
 *
 * Potential solutions to explore:
 * 1. Modify llmStore.selectThread() to check ui.isSmall and navigate to client action directly
 * 2. Add proper guards in setAsDiscussThread() override to prevent loops
 * 3. Use a different approach for mobile navigation (e.g., custom modal/overlay)
 * 4. Check how Odoo's discuss.channel handles this and replicate the pattern
 *
 * For now, mobile users can use the form view to access threads. Desktop works correctly.
 */
patch(Thread.prototype, {
  /**
   * Update action context with active_id
   * @param {String} activeId - Active ID to set
   */
  _updateActionContext(activeId) {
    if (
      !this.store?.action_discuss_id ||
      !this.store.env?.services?.action?.currentController?.action
    ) {
      return;
    }

    const currentAction =
      this.store.env.services.action.currentController.action;
    if (currentAction.id !== this.store.action_discuss_id) {
      return;
    }

    // Keep the action stack up to date (used by breadcrumbs).
    if (!currentAction.context) {
      currentAction.context = {};
    }
    currentAction.context.active_id = activeId;
  },

  /**
   * Override setActiveURL to handle llm.thread model
   */
  setActiveURL() {
    // Handle llm.thread model specifically
    if (this.model === "llm.thread") {
      try {
        const activeId = `llm.thread_${this.id}`;

        // Safely update router state
        if (router && router.pushState) {
          router.pushState({ active_id: activeId });
        }

        // Update action context if available
        this._updateActionContext(activeId);
      } catch (error) {
        console.warn("Error updating URL for LLM thread:", error);
        // Continue without failing
      }
    } else {
      // For all other models, use the original implementation
      super.setActiveURL();
    }
  },
});
