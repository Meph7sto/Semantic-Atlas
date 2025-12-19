import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src')
        }
    },
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://localhost:5001',
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
            '/api': {
                target: 'http://localhost:5001',
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
