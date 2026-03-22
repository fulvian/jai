/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://100.99.43.29:3030'}/api/:path*`,
            },
        ];
    },
};

module.exports = nextConfig;
