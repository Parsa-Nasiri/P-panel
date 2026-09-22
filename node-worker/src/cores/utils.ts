// Verdent fork: relay-only utilities. Panel-only helpers (routing rules,
// remark generation, config address generation, proxy-param parsing) were
// removed with the customer-facing panel — the relay path needs only DNS
// resolution and address parsing.

import { safeError } from '@common';

interface DnsResult {
    ipv4: string[];
    ipv6: string[];
}

export async function resolveDNS(domain: string, onlyIPv4 = false): Promise<DnsResult> {
    const dohBaseURL = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}`;
    const dohURLs = {
        ipv4: `${dohBaseURL}&type=A`,
        ipv6: `${dohBaseURL}&type=AAAA`,
    };

    try {
        const ipv4 = await fetchDNSRecords(dohURLs.ipv4, 1);
        const ipv6 = onlyIPv4 ? [] : await fetchDNSRecords(dohURLs.ipv6, 28);
        return { ipv4, ipv6 };
    } catch (error) {
        throw new Error(`Error resolving DNS for ${domain}: ${safeError(error)}`);
    }
}

export async function fetchDNSRecords(url: string, recordType: number): Promise<string[]> {
    try {
        const response = await fetch(url, { headers: { accept: 'application/dns-json' } });
        const data: any = await response.json();

        if (!data.Answer) return [];

        return data.Answer
            .filter((record: any) => record.type === recordType)
            .map((record: any) => record.data);

    } catch (error) {
        throw new Error(`Failed to fetch DNS records from ${url}: ${safeError(error)}`);
    }
}

export function isDomain(address: string): boolean {
    if (!address) return false;
    const domainRegex = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;
    return domainRegex.test(address);
}

export function isIPv4(address: string): boolean {
    const ipv4Pattern = /^(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?:\/([0-9]|[1-2][0-9]|3[0-2]))?$/;
    return ipv4Pattern.test(address);
}

export function isIPv6(address: string): boolean {
    const ipv6Pattern = /^\[(?:(?:[a-fA-F0-9]{1,4}:){7}[a-fA-F0-9]{1,4}|(?:[a-fA-F0-9]{1,4}:){1,7}:|::(?:[a-fA-F0-9]{1,4}:){0,7}|(?:[a-fA-F0-9]{1,4}:){1,6}:[a-fA-F0-9]{1,4}|(?:[a-fA-F0-9]{1,4}:){1,5}(?::[a-fA-F0-9]{1,4}){1,2}|(?:[a-fA-F0-9]{1,4}:){1,4}(?::[a-fA-F0-9]{1,4}){1,3}|(?:[a-fA-F0-9]{1,4}:){1,3}(?::[a-fA-F0-9]{1,4}){1,4}|(?:[a-fA-F0-9]{1,4}:){1,2}(?::[a-fA-F0-9]{1,4}){1,5}|[a-fA-F0-9]{1,4}:(?::[a-fA-F0-9]{1,4}){1,6})\](?:\/(1[0-1][0-9]|12[0-8]|[0-9]?[0-9]))?$/;
    return ipv6Pattern.test(address);
}

export function parseHostPort(input: string, brackets?: boolean): { host: string, port: number } {
    const regex = /^(?:\[(?<ipv6>.+?)\]|(?<host>[^:]+))(:(?<port>\d+))?$/;
    const match = input.match(regex);

    if (!match || !match.groups) return { host: '', port: 0 };
    const { ipv6, host: plainHost, port: portStr } = match.groups;

    let host = ipv6 ?? plainHost ?? '';
    if (brackets && ipv6) host = `[${ipv6}]`;
    const port = portStr ? Number(portStr) : 0;

    return { host, port };
}

Array.prototype.concatIf = function <T>(condition: boolean, concat: T | T[]): T[] {
    if (!condition) return this;
    if (Array.isArray(concat)) return [...this, ...concat];
    return [...this, concat]
}

Object.prototype.omitEmpty = function <T>(): T | undefined {
    if (Object.keys(this).length === 0) return undefined;
    return this as T;
}
