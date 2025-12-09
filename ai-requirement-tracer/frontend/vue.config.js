const { defineConfig } = require('@vue/cli-service')

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    port: 8080,
    host: '0.0.0.0',
    allowedHosts: 'all',
    client: {
      overlay: {
        warnings: false,
        errors: false,
        runtimeErrors: false
      }
    },
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        ws: true
      }
    }
  },
  publicPath: process.env.NODE_ENV === 'production' ? '/static/' : '/'
})
