import { defineConfig } from 'vitest/config';

export default defineConfig({
    test: {
        globals: true,
        environment: 'node',
        testTimeout: 120000, // 2 minuti per test E2E
        hookTimeout: 30000,
        include: ['src/**/*.test.ts'],
        exclude: ['node_modules', 'dist'],
        coverage: {
            provider: 'v8',
            reporter: ['text', 'html'],
            include: ['src/**/*.ts'],
            exclude: ['src/**/*.test.ts', 'src/__tests__/**'],
        },
        reporters: ['verbose'],
        pool: 'forks', // Usa forks per isolamento
        poolOptions: {
            forks: {
                singleFork: true, // Un solo fork per evitare conflitti di porta
            },
        },
    },
});
