declare global {
    interface Env {
        readonly CF_PAGES: string;
        readonly kv: KVNamespace;
        readonly SESSION_COUNTER?: DurableObjectNamespace;
        readonly provisioned?: string;
    }

    interface Array<T> {
        concatIf<T>(condition: boolean, concat: T | T[]): T[];
    }

    interface Object {
        omitEmpty<T>(): T | undefined;
    }
}

export { };
