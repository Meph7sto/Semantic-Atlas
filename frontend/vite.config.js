import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const devServerPort = Number(process.env.VITE_DEV_SERVER_PORT || 8008)
const devServerHost = process.env.VITE_DEV_SERVER_HOST || '0.0.0.0'
const hmrClientPort = Number(process.env.VITE_PUBLIC_PORT || devServerPort)
const usePolling = process.env.VITE_USE_POLLING === '1'
const pollInterval = Number(process.env.VITE_POLL_INTERVAL || 300)

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src')
        }
    },
    server: {
        host: devServerHost,
        port: devServerPort,
        strictPort: true,
        allowedHosts: true,
        hmr: {
            clientPort: hmrClientPort
        },
        watch: usePolling ? {
            usePolling: true,
            interval: pollInterval
        } : undefined,
        proxy: {
            '/api/v2/': {
                target: 'http://localhost:5002',
                changeOrigin: true
            },
            '/inference': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/inference/, '')
            }
        }
    },
    preview: {
        port: 8008,
        proxy: {
            '/api/v2/': {
                target: 'http://localhost:5002',
                changeOrigin: true
            },
            '/inference': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/inference/, '')
            }
        }
    }
})
