package service

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/mhsanaei/3x-ui/v2/logger"
)

type aimiliNode struct {
	ID           string `json:"id"`
	Country      string `json:"country_long"`
	CountryShort string `json:"country_short"`
	HostName     string `json:"host_name"`
	IP           string `json:"ip"`
	Score        int    `json:"score"`
	Ping         int    `json:"ping"`
	Sessions     int    `json:"sessions"`
	ISP          string `json:"owner"`
	ASN          string `json:"asn"`
	ASName       string `json:"as_name"`
	IPType       string `json:"ip_type"`
	LatencyMs    int    `json:"latency_ms"`
	Proto        string `json:"proto"`
	RemoteHost   string `json:"remote_host"`
	RemotePort   int    `json:"remote_port"`
	ConfigFile   string `json:"config_file"`
	ProbeStatus  string `json:"probe_status"`
	Active       bool   `json:"active"`
}

type aimiliNodesResponse struct {
	Nodes []aimiliNode  `json:"nodes"`
	State map[string]any `json:"state"`
}

func getAimiliToken() string {
	return os.Getenv("X_MILI_TOKEN")
}

func getAimiliAPIURL() string {
	if url := os.Getenv("AIMILI_NODE_API"); url != "" {
		return strings.TrimRight(url, "/")
	}
	return ""
}

func fetchAimiliNodes(apiURL string) ([]VPNGateServer, error) {
	client := &http.Client{Timeout: 15 * time.Second}
	req, err := http.NewRequest("GET", apiURL+"/api/nodes", nil)
	if err != nil {
		return nil, fmt.Errorf("aimili-vpngate request create failed: %w", err)
	}
	if token := getAimiliToken(); token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("aimili-vpngate API request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("aimili-vpngate API returned %s", resp.Status)
	}

	var result aimiliNodesResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("aimili-vpngate API JSON parse failed: %w", err)
	}

	servers := make([]VPNGateServer, 0, len(result.Nodes))
	for _, n := range result.Nodes {
		if n.ConfigFile == "" {
			continue
		}
		countryLong := n.Country
		if countryLong == "" {
			countryLong = n.CountryShort
		}
		ipType := n.IPType
		if ipType == "" || ipType == "unknown" {
			ipType = "Unknown"
		}

		localPing := int64(n.LatencyMs)
		if localPing <= 0 {
			localPing = int64(n.Ping)
		}
		if localPing <= 0 {
			localPing = -1
		}

		server := VPNGateServer{
			HostName:          n.HostName,
			IP:                n.IP,
			CountryLong:       countryLong,
			CountryShort:      n.CountryShort,
			CountryShortLower: strings.ToLower(n.CountryShort),
			NumSessions:       int64(n.Sessions),
			ISP:               n.ISP,
			ASN:               n.ASN,
			IPType:            ipType,
			LocalPing:         localPing,
			Proto:             n.Proto,
			Port:              fmt.Sprintf("%d", n.RemotePort),
			OpenVPNConfig:     "",
		}
		servers = append(servers, server)
	}

	logger.Infof("[AimiliVPN] Fetched %d nodes from aimili-vpngate API", len(servers))
	return servers, nil
}

func loadAimiliVPNServers() ([]VPNGateServer, error) {
	apiURL := getAimiliAPIURL()
	if apiURL == "" {
		return nil, fmt.Errorf("AIMILI_NODE_API is not configured")
	}
	return fetchAimiliNodes(apiURL)
}
