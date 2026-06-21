/** @odoo-module **/

import { ActionContainer } from "@web/webclient/actions/action_container";
import { MainComponentsContainer } from "@web/core/main_components_container";
import { useOwnDebugContext } from "@web/core/debug/debug_context";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart } from "@odoo/owl";
import { session } from "@web/session";

export class MarketplaceWebClient extends Component {
    static props = {};
    static components = { ActionContainer, MainComponentsContainer };
    static template = "website_sale_marketplace.MarketplaceWebClient";

    setup() {
        this.actionService = useService("action");
        useOwnDebugContext({ categories: ["default"] });

        onWillStart(async () => {
            await this.loadAction();
        });
    }

    async loadAction() {
        const actionName = session.action_name;
        const vendorPartnerId = session.vendor_partner_id;

        if (actionName) {
            await this.actionService.doAction(actionName, {
                clearBreadcrumbs: true,
                additionalContext: {
                    default_marketplace_vendor_id: vendorPartnerId,
                    vendor_partner_id: vendorPartnerId,
                },
            });
        }
    }
}
