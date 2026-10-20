<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AuthorPreview, AuthorDetail } from '@/types'
import AuthorCard from './AuthorCard.vue'
import CarouselArrow from '@/components/common/CarouselArrow.vue'
import { compareAuthorNames } from '@/utils/format-utils'
import { useDisplay } from 'vuetify'
import { LAYOUT } from '@/constants/theme.ts'

const { mobile } = useDisplay()

const props = defineProps<{
  authors: AuthorPreview[]
  currentAuthor: AuthorDetail
}>()

const { t } = useI18n()

const sortedAuthors = computed(() => [...props.authors].sort((a, b) => compareAuthorNames(a, b)))

const currentIndex = computed(() =>
  sortedAuthors.value.findIndex((a) => a.id === props.currentAuthor.id)
)

const trackRef = ref<HTMLElement | null>(null)
const hasPrevious = ref(false)
const hasNext = ref(false)

function updateScrollState() {
  const track = trackRef.value
  if (!track) return
  hasPrevious.value = track.scrollLeft > 0
  hasNext.value = track.scrollLeft + track.clientWidth < track.scrollWidth - 1
}

function scrollByCell(direction: 1 | -1) {
  const track = trackRef.value
  if (!track) return
  const cell = track.querySelector('.carousel-cell--others')
  const cellWidth = cell ? cell.clientWidth : track.clientWidth / 5
  track.scrollBy({ left: direction * cellWidth, behavior: 'smooth' })
}

function shiftLeft() {
  scrollByCell(-1)
}

function shiftRight() {
  scrollByCell(1)
}

onMounted(() => {
  updateScrollState()
  window.addEventListener('resize', updateScrollState)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateScrollState)
})

// Scroll to current author
watch(
  currentIndex,
  async () => {
    await nextTick()
    if (trackRef.value) {
      const currentCell = trackRef.value.querySelector('.carousel-cell--current') as HTMLElement
      if (currentCell) {
        if (mobile.value) {
          trackRef.value.scrollTo({ left: currentCell.offsetLeft })
        } else {
          trackRef.value.scrollTo({ left: currentCell.offsetLeft - currentCell.clientWidth * 2 })
        }
        updateScrollState()
      }
    }
  },
  { immediate: true }
)
</script>

<template>
  <div class="author-detail-carousel">
    <div class="author-detail-carousel--inner">
      <div class="carousel-arrow-wrapper carousel-arrow-wrapper--left" v-if="!mobile">
        <carousel-arrow
          direction="left"
          :disabled="!hasPrevious"
          :ariaLabel="t('common.previous')"
          @click="shiftLeft"
        />
      </div>

      <div class="carousel-track-wrapper">
        <div ref="trackRef" class="carousel-track" @scroll.passive="updateScrollState">
          <template v-for="author in sortedAuthors" :key="author.id">
            <div
              class="carousel-cell"
              :class="{ 'carousel-cell--current': author.id === currentAuthor.id }"
            >
              <author-card
                :author="author"
                :variant="mobile ? 'row' : 'mini'"
                :navigate="author.id !== currentAuthor.id"
                :selected="author.id === currentAuthor.id"
              />
            </div>
          </template>
        </div>
      </div>

      <div class="carousel-arrow-wrapper carousel-arrow-wrapper--right" v-if="!mobile">
        <carousel-arrow
          direction="right"
          :disabled="!hasNext"
          :ariaLabel="t('common.next')"
          @click="shiftRight"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.author-detail-carousel {
  border-top: 0.5px solid rgb(var(--v-theme-grid));
  background-color: rgb(var(--v-theme-bgd2));
  width: 100vw;
  margin-left: calc(50% - 50vw);
  margin-right: calc(50% - 50vw);
  margin-bottom: -2rem;
}

.author-detail-carousel--inner {
  padding: 0 v-bind(LAYOUT.VIEW_PADDING_HORIZONTAL);
  max-width: v-bind(LAYOUT.MAX_CONTENT_WIDTH);
  margin-inline: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
  padding: 5rem 0;
}

.carousel-track-wrapper {
  width: calc(100% - 170px);
  flex-shrink: 0;
  display: flex;
}

.carousel-track {
  display: flex;
  position: relative;
  width: 100%;
  align-items: stretch;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}

.carousel-track::-webkit-scrollbar {
  display: none;
}

.carousel-arrow-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}

.carousel-cell {
  /* Every cell needs this, not just the current one — otherwise
     scroll-snap-type: x mandatory (below) has only one valid snap point
     and snaps straight back to it after any other scroll attempt,
     including the arrow buttons. */
  scroll-snap-align: start;
  display: flex;
  flex: 0 0 20%;
}

@media (max-width: 767px) {
  .author-detail-carousel {
    width: 100vw;
    margin-left: calc(50% - 50vw);
    margin-right: calc(50% - 50vw);
  }

  .carousel-track-wrapper {
    width: 100%;
  }

  .carousel-cell {
    flex: 0 0 75%;
  }
}
</style>
