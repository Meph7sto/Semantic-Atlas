import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { URL, URLSearchParams } from 'node:url'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import axios from 'axios'
import { createMemoryHistory, createRouter } from 'vue-router'

function dependency(exports, context) {
    return new SyntheticModule(Object.keys(exports), function () {
        for (const [key, value] of Object.entries(exports)) {
            this.setExport(key, value)
        }
    }, { context })
}

async function loadRouter(authorized) {
    let validationCount = 0
    const store = {
        init() {},
        async ensureValidSession() {
            validationCount++
            return authorized
        }
    }
    const source = await readFile(new URL('../src/router/index.js', import.meta.url), 'utf8')
    const module = new SourceTextModule(source, {
        initializeImportMeta(meta) {
            meta.env = { BASE_URL: '/' }
        }
    })
    await module.link((specifier) => {
        if (specifier === 'vue-router') {
            return dependency({ createRouter, createWebHistory: createMemoryHistory })
        }
        if (specifier === '@/stores/auth.js') {
            return dependency({ useAuthStore: () => store })
        }
        assert.ok(specifier.endsWith('.vue'), `Unexpected dependency: ${specifier}`)
        return dependency({ default: {} })
    })
    await module.evaluate()
    return { router: module.namespace.default, validationCount: () => validationCount }
}

for (const path of ['/alpha/conflict', '/alpha/chat?session_id=meeting-1', '/beta/dashboard']) {
    test(`unauthenticated navigation to ${path} opens login with the return target`, async () => {
        const { router } = await loadRouter(false)
        await router.push(path)
        assert.equal(router.currentRoute.value.name, 'beta-login')
        assert.equal(router.currentRoute.value.query.redirect, path)
    })
}

test('authenticated users can still enter Alpha', async () => {
    const { router } = await loadRouter(true)
    await router.push('/alpha/conflict')
    assert.equal(router.currentRoute.value.fullPath, '/alpha/conflict')
})

for (const path of ['/guide', '/beta/login?redirect=/alpha/conflict']) {
    test(`public route ${path} does not require authentication`, async () => {
        const { router, validationCount } = await loadRouter(false)
        await router.push(path)
        assert.equal(router.currentRoute.value.fullPath, path)
        assert.equal(validationCount(), 0)
    })
}

async function loadRequest(path) {
    const location = new URL(path, 'http://localhost:8008')
    const redirects = []
    const events = []
    const storage = new Map([
        ['token', 'expired-token'], ['user', '{}'], ['actor', 'test'], ['role', 'member']
    ])
    const context = createContext({
        URLSearchParams,
        CustomEvent: class { constructor(type) { this.type = type } },
        localStorage: {
            getItem: (key) => storage.get(key),
            removeItem: (key) => storage.delete(key)
        },
        window: {
            location: {
                pathname: location.pathname,
                search: location.search,
                assign: (target) => redirects.push(target)
            },
            dispatchEvent: (event) => events.push(event.type)
        }
    })
    const source = await readFile(new URL('../src/api/request.js', import.meta.url), 'utf8')
    const module = new SourceTextModule(source, { context })
    await module.link((specifier) => {
        assert.equal(specifier, 'axios')
        return dependency({ default: axios }, context)
    })
    await module.evaluate()
    return { request: module.namespace, redirects, events, storage }
}

for (const path of ['/alpha', '/alpha/conflict', '/alpha/chat?session_id=meeting 1', '/beta/dashboard']) {
    test(`401 at ${path} clears the expired session and redirects to login`, async () => {
        const { request, redirects, events, storage } = await loadRequest(path)
        await assert.rejects(request.api.get('/session', {
            adapter: async () => { throw { response: { status: 401, data: {} }, config: {} } }
        }))
        assert.equal(storage.size, 0)
        assert.deepEqual(events, ['semantic-atlas:auth-cleared'])
        assert.equal(redirects.length, 1)
        const target = new URL(redirects[0], 'http://localhost:8008')
        const original = new URL(path, 'http://localhost:8008')
        assert.equal(target.pathname, '/beta/login')
        assert.equal(target.searchParams.get('redirect'), original.pathname + original.search)
    })
}

for (const path of ['/guide', '/guide/videos', '/beta/login?redirect=/alpha/conflict']) {
    test(`401 at public route ${path} does not create a redirect loop`, async () => {
        const { request, redirects, storage } = await loadRequest(path)
        request.handleUnauthorized()
        assert.equal(storage.size, 0)
        assert.deepEqual(redirects, [])
    })
}

test('session verification can handle a 401 without a hard navigation', async () => {
    const { request, redirects, storage } = await loadRequest('/alpha/conflict')
    await assert.rejects(request.api.get('/auth/verify', {
        adapter: async () => {
            throw { response: { status: 401, data: {} }, config: { skipAuthRedirect: true } }
        }
    }))
    assert.equal(storage.size, 0)
    assert.deepEqual(redirects, [])
})
