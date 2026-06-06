/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

/**
 * GPU Dashboard – Owl component for real-time GPU cluster management.
 * Handles network scan, node removal/reassignment, fine-tuning launch,
 * and schedule toggling.
 * FUTURE: Add live utilisation graphs via Prometheus WebSocket.
 */
export class GPUDashboard extends Component {
    static template = "gpu_admin_panel.GPUDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            clusters: [],
            nodes: [],
            datasets: [],
            internalNodes: [],
            schedule: [],
            wireguard_peers: [],
            selectedDatasetId: null,
            baseModel: 'deepseek-ai/DeepSeek-R1-Distill-Qwen-14B',
            mode: 'multi',
            selectedGpuIds: [],
            finetuneJobId: null,
            finetuneStatus: null,
        });
        onWillStart(async () => { await this.loadData(); });
    }

    async loadData() {
        const companyId = this.env.user.companyId;
        this.state.clusters = await this.orm.searchRead("gpu.cluster", [["company_id","=",companyId]], ["id","name","trust_mode","total_vram_gb"]);
        this.state.nodes = await this.orm.searchRead("gpu.node", [["cluster_id.company_id","=",companyId]], ["id","hostname","pool","total_vram_gb","gpu_count","status","uptime_hours","tokens_served","token_earnings"]);
        this.state.internalNodes = this.state.nodes.filter(n => n.pool === 'internal');
        this.state.datasets = await this.orm.searchRead("ft.dataset", [["field_id.company_id","=",companyId]], ["id","name"]);
        this.state.schedule = await this.orm.searchRead("gpu.sharing.schedule", [["cluster_id.company_id","=",companyId]], ["id","day_of_week","start_time","end_time","is_enabled"]);
        // WireGuard peers (simplified)
    }

    statusColor(status) {
        const map = { online: "success", offline: "danger", degraded: "warning", maintenance: "info" };
        return map[status] || "secondary";
    }

    nodeCountByStatus(status) {
        return this.state.nodes.filter(n => n.status === status).length;
    }

    async scanNetwork() {
        const clusterId = this.state.clusters[0]?.id;
        if (!clusterId) { this.notification.add("No cluster configured.", { type: "warning" }); return; }
        try {
            await this.orm.call("gpu.cluster", "action_scan_network", [clusterId]);
            this.notification.add("Network scan complete.", { type: "success" });
            await this.loadData();
        } catch (e) { this.notification.add("Scan failed: " + e.message, { type: "danger" }); }
    }

    addNodeManually() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Add GPU Node",
            res_model: "gpu.node",
            view_mode: "form",
            target: "new",
            context: { default_cluster_id: this.state.clusters[0]?.id },
        });
    }

    async removeNode(nodeId) {
        try {
            await this.orm.unlink("gpu.node", [nodeId]);
            this.notification.add("Node removed.", { type: "success" });
            await this.loadData();
        } catch (e) { this.notification.add("Failed to remove node: " + e.message, { type: "danger" }); }
    }

    async reassignNode(nodeId) {
		// Open wizard to reassign pool
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Reassign Node Pool",
            res_model: "gpu.node",
            res_id: nodeId,
            view_mode: "form",
            target: "new",
        });
    }

    async toggleSchedule(scheduleId) {
        const record = this.state.schedule.find(s => s.id === scheduleId);
        try {
            await this.orm.write("gpu.sharing.schedule", [scheduleId], { is_enabled: !record.is_enabled });
            await this.loadData();
        } catch (e) { this.notification.add("Toggle failed: " + e.message, { type: "danger" }); }
    }

    async startFineTuning() {
        const clusterId = this.state.clusters[0]?.id;
        if (!clusterId || !this.state.selectedDatasetId || this.state.selectedGpuIds.length === 0) {
            this.notification.add("Please select a dataset and at least one GPU.", { type: "warning" });
            return;
        }
        try {
            const result = await this.orm.call("gpu.cluster", "start_finetune", [clusterId], {
                dataset_id: this.state.selectedDatasetId,
                base_model: this.state.baseModel,
                mode: this.state.mode,
                gpu_ids: this.state.selectedGpuIds,
            });
            this.state.finetuneJobId = result.job_id;
            this.state.finetuneStatus = "running";
            this.notification.add("Fine-tuning started. Job ID: " + result.job_id, { type: "success" });
        } catch (e) { this.notification.add("Failed to start fine-tuning: " + e.message, { type: "danger" }); }
    }

    async deployModel() {
        if (!this.state.finetuneJobId) return;
        try {
            const result = await this.orm.call("gpu.cluster", "deploy_finetuned_model", [this.state.finetuneJobId]);
            this.notification.add("Model deployed as provider ID " + result.provider_id, { type: "success" });
        } catch (e) { this.notification.add("Deploy failed: " + e.message, { type: "danger" }); }
    }
}

registry.category("actions").add("gpu_dashboard", GPUDashboard);