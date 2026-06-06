/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class WireGuardManager extends Component {
    static template = "gpu_admin_panel.WireGuardManager";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            peers: [],
            controllerPublicKey: "",
            meshSubnet: "10.100.0.0/24",
            listenPort: 51820,
        });
        onWillStart(async () => { await this.loadPeers(); });
    }

    async loadPeers() {
        try {
            const clusters = await this.orm.searchRead("gpu.cluster",
                [["company_id", "=", this.env.user.companyId]],
                ["wireguard_controller_public_key", "wireguard_mesh_subnet", "wireguard_listen_port"]);
            if (clusters.length) {
                this.state.controllerPublicKey = clusters[0].wireguard_controller_public_key;
                this.state.meshSubnet = clusters[0].wireguard_mesh_subnet;
                this.state.listenPort = clusters[0].wireguard_listen_port;
            }
            const peers = await this.orm.call("gpu.cluster", "get_wireguard_peers", [clusters[0]?.id]);
            this.state.peers = peers || [];
        } catch (e) {
            this.notification.add("Failed to load peers: " + e.message, { type: "danger" });
        }
    }

    async revokePeer(publicKey) {
        try {
            await this.orm.call("gpu.cluster", "revoke_wireguard_peer", [publicKey]);
            this.notification.add("Peer revoked.", { type: "success" });
            await this.loadPeers();
        } catch (e) {
            this.notification.add("Revoke failed: " + e.message, { type: "danger" });
        }
    }

    async generateKeys() {
        try {
            const result = await this.orm.call("gpu.cluster", "action_generate_wireguard_keys", []);
        /** const result = await this.orm.call("gpu.cluster", "action_generate_wireguard_keys", [this.state.clusterId]);  **/
            this.notification.add("New WireGuard keypair generated.", { type: "success" });
            await this.loadPeers();
        } catch (e) {
            this.notification.add("Key generation failed: " + e.message, { type: "danger" });
        }
    }

    async downloadConfigs() {
        try {
            const config = await this.orm.call("gpu.cluster", "get_wireguard_configs", []);
        /** const config = await this.orm.call("gpu.cluster", "get_wireguard_configs", [this.state.clusterId]);   **/
            const blob = new Blob([config], { type: "text/plain" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "wireguard_peers.conf";
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            this.notification.add("Download failed: " + e.message, { type: "danger" });
        }
    }
}