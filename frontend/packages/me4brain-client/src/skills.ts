/**
 * Skills Namespace
 * 
 * Provides access to Skills API endpoints for:
 * - Listing and managing crystallized skills
 * - HITL approval workflow for pending skills
 * - Skills statistics
 * 
 * @since v0.15.0
 */

import type { Me4BrAInClient } from './client.js';
import type {
    PendingSkill,
    ApprovalRequest,
    ApprovalStats,
    SkillInfo,
    SkillListResponse,
} from './types.js';

export class SkillsNamespace {
    constructor(private client: Me4BrAInClient) { }

    // ==========================================================================
    // SKILL MANAGEMENT
    // ==========================================================================

    /**
     * List all skills.
     * 
     * @param type - Filter by type: 'explicit' | 'crystallized'
     * @param enabledOnly - If true, show only enabled skills (default: true)
     * @returns List of skills
     */
    async list(type?: 'explicit' | 'crystallized', enabledOnly = true): Promise<SkillListResponse> {
        const params: Record<string, string> = {};
        if (type) params.type = type;
        if (!enabledOnly) params.enabled_only = 'false';

        const response = await this.client.request<{
            skills: Array<{
                id: string;
                name: string;
                description: string;
                type: 'explicit' | 'crystallized';
                enabled: boolean;
                usage_count: number;
                success_rate: number;
                confidence: number;
                version?: string;
            }>;
            total: number;
        }>('GET', '/skills', { params });

        return {
            skills: response.skills.map(s => ({
                id: s.id,
                name: s.name,
                description: s.description,
                type: s.type,
                enabled: s.enabled,
                usageCount: s.usage_count,
                successRate: s.success_rate,
                confidence: s.confidence,
                version: s.version,
            })),
            total: response.total,
        };
    }

    /**
     * Get a specific skill by ID.
     * 
     * @param skillId - Skill ID
     * @returns Skill info
     */
    async get(skillId: string): Promise<SkillInfo> {
        const response = await this.client.request<{
            id: string;
            name: string;
            description: string;
            type: 'explicit' | 'crystallized';
            enabled: boolean;
            usage_count: number;
            success_rate: number;
            confidence: number;
            version?: string;
        }>('GET', `/skills/${skillId}`);

        return {
            id: response.id,
            name: response.name,
            description: response.description,
            type: response.type,
            enabled: response.enabled,
            usageCount: response.usage_count,
            successRate: response.success_rate,
            confidence: response.confidence,
            version: response.version,
        };
    }

    /**
     * Toggle skill enabled/disabled state.
     * 
     * @param skillId - Skill ID
     * @param enabled - New enabled state
     * @returns Updated skill
     */
    async toggle(skillId: string, enabled: boolean): Promise<SkillInfo> {
        const response = await this.client.request<{
            id: string;
            name: string;
            description: string;
            type: 'explicit' | 'crystallized';
            enabled: boolean;
            usage_count: number;
            success_rate: number;
            confidence: number;
            version?: string;
        }>('PATCH', `/skills/${skillId}`, {
            body: { enabled },
        });

        return {
            id: response.id,
            name: response.name,
            description: response.description,
            type: response.type,
            enabled: response.enabled,
            usageCount: response.usage_count,
            successRate: response.success_rate,
            confidence: response.confidence,
            version: response.version,
        };
    }

    /**
     * Delete a skill.
     * 
     * @param skillId - Skill ID to delete
     */
    async delete(skillId: string): Promise<void> {
        await this.client.request('DELETE', `/skills/${skillId}`);
    }

    // ==========================================================================
    // HITL APPROVAL WORKFLOW
    // ==========================================================================

    /**
     * List skills pending HITL approval.
     * 
     * Skills with CONFIRM risk level wait here for human review.
     * 
     * @returns List of pending skills
     */
    async listPending(): Promise<PendingSkill[]> {
        const response = await this.client.request<Array<{
            id: string;
            name: string;
            description: string;
            risk_level: string;
            tool_chain: string[];
            status: string;
            created_at: string;
            reviewed_at?: string;
        }>>('GET', '/skills/pending');

        return response.map(s => ({
            id: s.id,
            name: s.name,
            description: s.description,
            riskLevel: s.risk_level as PendingSkill['riskLevel'],
            toolChain: s.tool_chain,
            status: s.status as PendingSkill['status'],
            createdAt: s.created_at,
            reviewedAt: s.reviewed_at,
        }));
    }

    /**
     * Approve a pending skill.
     * 
     * Approved skills will be persisted to disk and available for use.
     * 
     * @param skillId - Pending skill ID
     * @param options - Approval options
     * @returns Approval confirmation
     */
    async approve(skillId: string, options: ApprovalRequest = {}): Promise<{ message: string; skillId: string }> {
        const response = await this.client.request<{
            message: string;
            skill_id: string;
            status: string;
        }>('POST', `/skills/pending/${skillId}/approve`, {
            body: { note: options.note },
        });

        return {
            message: response.message,
            skillId: response.skill_id,
        };
    }

    /**
     * Reject a pending skill.
     * 
     * Rejected skills will not be saved.
     * 
     * @param skillId - Pending skill ID
     * @param options - Rejection options (reason)
     * @returns Rejection confirmation
     */
    async reject(skillId: string, options: ApprovalRequest = {}): Promise<{ message: string; skillId: string }> {
        const response = await this.client.request<{
            message: string;
            skill_id: string;
            status: string;
        }>('POST', `/skills/pending/${skillId}/reject`, {
            body: { note: options.note },
        });

        return {
            message: response.message,
            skillId: response.skill_id,
        };
    }

    /**
     * Get approval workflow statistics.
     * 
     * @returns Stats: pending, approved, rejected counts
     */
    async approvalStats(): Promise<ApprovalStats> {
        return this.client.request<ApprovalStats>('GET', '/skills/approval-stats');
    }
}
