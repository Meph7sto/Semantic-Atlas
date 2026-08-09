<script setup>
import { computed, nextTick, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft, Clapperboard, Play, Radio } from 'lucide-vue-next'
import audioTranscriptionVideo from '../../../docs/vedio/audio-transcription.mp4'
import requirementItemizationVideo from '../../../docs/vedio/requirement-itemization.mp4'
import requirementsAnalysisVideo from '../../../docs/vedio/requirements-analysis.mp4'

const videos = [
  {
    id: 'audio-transcription',
    number: '01',
    category: '信息采集',
    title: '音频转文字',
    description: '将会议录音转成文字，为后续的需求整理提供原始材料。',
    src: audioTranscriptionVideo
  },
  {
    id: 'requirement-itemization',
    number: '02',
    category: '需求整理',
    title: '需求条目化',
    description: '从会议文本中提取需求，并整理为便于审阅的独立条目。',
    src: requirementItemizationVideo
  },
  {
    id: 'requirements-analysis',
    number: '03',
    category: '需求分析',
    title: '需求分析',
    description: '对整理后的需求进行分析，查看系统给出的处理结果。',
    src: requirementsAnalysisVideo
  }
]

const currentIndex = ref(0)
const player = ref(null)
const currentVideo = computed(() => videos[currentIndex.value])

const selectVideo = async (index) => {
  if (currentIndex.value === index) {
    player.value?.play().catch(() => {})
    return
  }

  currentIndex.value = index
  await nextTick()
  player.value?.play().catch(() => {})
}
</script>

<template>
  <div class="video-showcase">
    <header class="showcase-header">
      <RouterLink to="/guide" class="back-link" aria-label="返回系统入口">
        <ArrowLeft aria-hidden="true" />
        <span>返回入口</span>
      </RouterLink>

      <div class="showcase-brand" aria-label="Semantic Atlas 演示视频">
        <span class="brand-primary">Semantic Atlas</span>
        <span class="brand-divider" aria-hidden="true"></span>
        <span class="brand-section">Demo Library</span>
      </div>

      <div class="video-count">
        <Clapperboard aria-hidden="true" />
        <span>3 个视频</span>
      </div>
    </header>

    <main class="showcase-layout">
      <section class="video-stage" aria-labelledby="current-video-title">
        <div class="stage-heading">
          <p>{{ currentVideo.category }} / {{ currentVideo.number }}</p>
          <h1 id="current-video-title">{{ currentVideo.title }}</h1>
          <span>{{ currentVideo.description }}</span>
        </div>

        <div class="player-frame">
          <video
            :key="currentVideo.id"
            ref="player"
            class="main-player"
            controls
            playsinline
            preload="metadata"
            :aria-label="`${currentVideo.title}演示视频`"
          >
            <source :src="currentVideo.src" type="video/mp4" />
            当前浏览器不支持视频播放。
          </video>
          <div class="player-caption">
            <span>{{ currentVideo.number }} / 03</span>
            <span>{{ currentVideo.title }}</span>
          </div>
        </div>
      </section>

      <aside class="video-playlist" aria-label="演示视频列表">
        <div class="playlist-heading">
          <div>
            <p>PLAYLIST</p>
            <h2>演示目录</h2>
          </div>
          <span>03</span>
        </div>

        <div class="playlist-items">
          <button
            v-for="(video, index) in videos"
            :key="video.id"
            type="button"
            class="playlist-item"
            :class="{ active: currentIndex === index }"
            :aria-current="currentIndex === index ? 'true' : undefined"
            @click="selectVideo(index)"
          >
            <span class="item-number">{{ video.number }}</span>
            <span class="item-copy">
              <strong>{{ video.title }}</strong>
              <small>{{ video.category }}</small>
            </span>
            <Radio v-if="currentIndex === index" class="item-icon is-active" aria-hidden="true" />
            <Play v-else class="item-icon" aria-hidden="true" />
          </button>
        </div>

        <p class="playlist-note">按顺序观看，可了解从会议录音到需求分析的完整流程。</p>
      </aside>
    </main>
  </div>
</template>

<style scoped>
.video-showcase {
  --ink: #18242b;
  --muted: #65727a;
  --line: #d8dddc;
  --paper: #f4f5f2;
  --accent: #c4692f;
  --signal: #2f8f89;
  height: 100vh;
  overflow-y: auto;
  background: var(--paper);
  color: var(--ink);
}

.showcase-header {
  position: sticky;
  top: 0;
  z-index: 10;
  min-height: 72px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 24px;
  padding: 14px 32px;
  border-bottom: 1px solid var(--line);
  background: rgba(244, 245, 242, 0.96);
  backdrop-filter: blur(12px);
}

.back-link,
.video-count,
.showcase-brand {
  display: inline-flex;
  align-items: center;
}

.back-link {
  width: fit-content;
  gap: 8px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
  transition: color 0.18s ease;
}

.back-link:hover {
  color: var(--ink);
}

.back-link svg,
.video-count svg {
  width: 17px;
  height: 17px;
}

.showcase-brand {
  gap: 12px;
  justify-content: center;
  white-space: nowrap;
}

.brand-primary {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 17px;
  font-weight: 700;
}

.brand-divider {
  width: 1px;
  height: 18px;
  background: #aeb6b6;
}

.brand-section {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.video-count {
  justify-self: end;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.showcase-layout {
  width: min(1440px, 100%);
  min-height: calc(100vh - 73px);
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 40px;
  padding: 36px 40px 48px;
}

.video-stage {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.stage-heading {
  margin-bottom: 22px;
}

.stage-heading p,
.playlist-heading p {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.stage-heading h1 {
  margin: 0 0 9px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 32px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: 0;
}

.stage-heading span {
  display: block;
  max-width: 680px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.7;
}

.player-frame {
  overflow: hidden;
  border: 1px solid #11191d;
  border-radius: 6px;
  background: #10171b;
  box-shadow: 0 18px 48px rgba(24, 36, 43, 0.18);
}

.main-player {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #080c0e;
  object-fit: contain;
}

.player-caption {
  min-height: 46px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  color: #dbe2e2;
  font-size: 12px;
}

.player-caption span:first-child {
  color: #8fbeb6;
  font-variant-numeric: tabular-nums;
}

.video-playlist {
  align-self: center;
  padding-left: 32px;
  border-left: 1px solid var(--line);
}

.playlist-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}

.playlist-heading h2 {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 0;
}

.playlist-heading > span {
  color: #a4adad;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 30px;
  line-height: 1;
}

.playlist-items {
  display: flex;
  flex-direction: column;
}

.playlist-item {
  position: relative;
  width: 100%;
  min-height: 84px;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 20px;
  align-items: center;
  gap: 12px;
  padding: 14px 10px;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: transparent;
  color: var(--ink);
  cursor: pointer;
  text-align: left;
  transition:
    background-color 0.18s ease,
    padding-left 0.18s ease;
}

.playlist-item:hover {
  background: rgba(255, 255, 255, 0.62);
}

.playlist-item.active {
  padding-left: 14px;
  background: #ffffff;
  box-shadow: inset 3px 0 0 var(--signal);
}

.item-number {
  color: #939e9f;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.item-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.item-copy strong {
  overflow: hidden;
  font-size: 14px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-copy small {
  color: var(--muted);
  font-size: 11px;
}

.item-icon {
  width: 17px;
  height: 17px;
  color: #98a2a2;
}

.item-icon.is-active {
  color: var(--signal);
}

.playlist-note {
  margin: 20px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}

@media (max-width: 960px) {
  .showcase-layout {
    grid-template-columns: 1fr;
    gap: 34px;
  }

  .video-playlist {
    width: 100%;
    padding: 28px 0 0;
    border-top: 1px solid var(--line);
    border-left: 0;
  }
}

@media (max-width: 640px) {
  .showcase-header {
    grid-template-columns: 1fr auto;
    padding: 12px 16px;
  }

  .showcase-brand {
    justify-self: end;
  }

  .brand-section,
  .video-count,
  .back-link span {
    display: none;
  }

  .brand-divider {
    display: none;
  }

  .showcase-layout {
    min-height: calc(100vh - 61px);
    padding: 28px 16px 40px;
  }

  .stage-heading h1 {
    font-size: 28px;
  }

  .player-caption {
    min-height: 42px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .back-link,
  .playlist-item {
    transition: none;
  }
}
</style>
