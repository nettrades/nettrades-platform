/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

export class GPUNetworkScan extends Component {
    static template = "gpu_admin_panel.GPUNetworkScan";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            discovered: [],
            scanning: false,
            selectedHosts: new Set(),
        });
    }

    async startScan() {
        this.state.scanning = true;
        try {
            const result = await this.orm.call("gpu.cluster", "action_scan_network", []);
            this.state.discovered = result.discovered || [];
        } catch (e) {
            this.notification.add("Scan error: " + e.message, { type: "danger" });
        } finally {
            this.state.scanning = false;
        }
    }

    toggleHost(ip) {
        if (this.state.selectedHosts.has(ip)) {
            this.state.selectedHosts.delete(ip);
        } else {
            this.state.selectedHosts.add(ip);
        }
    }

    async installSelected(pool) {
        for (const ip of this.state.selectedHosts) {
            try {
                await this.orm.call("gpu.cluster", "action_install_node", [ip, pool]);
            } catch (e) {
                this.notification.add("Install failed for " + ip + ": " + e.message, { type: "danger" });
            }
        }
        this.notification.add("Installation triggered for selected hosts.", { type: "success" });
    }
}

registry.category("actions").add("gpu_network_scan", GPUNetworkScan);