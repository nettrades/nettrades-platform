/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { _t } from "@web/core/l10n/translation";
import { whenReady } from "@odoo/owl";
import { mountComponent } from "@web/env";
import { makeEnv, startServices } from "@web/env";
import { session } from "@web/session";

/**
 * Product Portal WebClient
 * Embeds the Odoo backend product views in the portal interface
 */
class ProductPortalWebClient extends WebClient {
    setup() {
        super.setup();
        this.title.setParts({ zopenerp: _t("My Products") });
    }
}

/**
 * Initialize the Product Portal
 */
async function initProductPortal() {
    const container = document.getElementById("marketplace_product_portal_container");

    if (!container) {
        console.error("Product portal container not found");
        return;
    }

    // Fetch the action configuration from the server
    let action;
    try {
        const response = await fetch("/my/products/get_action", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {},
            }),
        });

        const result = await response.json();

        if (result.error) {
            console.error("Error fetching action:", result.error);
            container.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <strong>Error:</strong> ${result.error.data.message || "Unable to load products"}
                </div>
            `;
            return;
        }

        action = result.result;
    } catch (error) {
        console.error("Error fetching action:", error);
        container.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <strong>Error:</strong> Unable to load products. Please try again.
            </div>
        `;
        return;
    }

    // Start services
    const env = await makeEnv();
    await startServices(env);

    // Mount the WebClient
    const webClient = await mountComponent(ProductPortalWebClient, container, { env });

    // Open the action
    if (action) {
        await webClient.loadState({
            action: action.id,
            actionStack: [
                {
                    action,
                    displayName: action.name,
                    view_type: action.views[0][1],
                }
            ],
        });
    }
}

// Initialize when DOM is ready
whenReady(() => {
    const container = document.getElementById("marketplace_product_portal_container");
    if (container) {
        initProductPortal();
    }
});
