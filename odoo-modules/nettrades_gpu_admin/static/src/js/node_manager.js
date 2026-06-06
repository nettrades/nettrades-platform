/** @odoo-module **/
import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class GPUNodeManager extends Component {
    static template = "gpu_admin_panel.GPUNodeManager";
    static props = ["nodeId"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            node: null,
            pools: [
                { value: "internal", label: "Pool A – Internal" },
                { value: "public", label: "Pool B – Public Sharing" },
            ],
            runtimes: [
                { value: "gvisor", label: "gVisor (recommended)" },
                { value: "docker", label: "Docker (trusted only)" },
            ],
        });
        onMounted(() => this.loadNode());
    }

    async loadNode() {
        const fields = ["hostname", "ip_address", "pool", "container_runtime", "gpu_count", "total_vram_gb", "status", "reputation_score"];
        const [node] = await this.orm.read("gpu.node", [this.props.nodeId], fields);
        if (node) this.state.node = node;
    }

    async onPoolChange(ev) {
        const newPool = ev.target.value;
        try {
            await this.orm.call("gpu.node", "action_reassign_pool", [this.props.nodeId, newPool]);
            this.notification.add("Pool changed successfully.", { type: "success" });
            await this.loadNode();
        } catch (e) {
            this.notification.add(e.message, { type: "danger" });
        }
    }

    async onRuntimeChange(ev) {
        const newRuntime = ev.target.value;
        try {
            await this.orm.write("gpu.node", [this.props.nodeId], { container_runtime: newRuntime });
            this.notification.add("Runtime updated.", { type: "success" });
        } catch (e) {
            this.notification.add(e.message, { type: "danger" });
        }
    }
}