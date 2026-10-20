<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AVATAR_SIZES, ICON_SIZES } from '@/constants/theme'
import { normalizeImagePath } from '@/utils/format-utils'

interface Props {
  portraitPath?: string | null
  name: string
  size?: 'small' | 'medium' | 'large' | 'xlarge'
}

const props = withDefaults(defineProps<Props>(), {
  portraitPath: null,
  size: 'large'
})

const imgFailed = ref(false)
watch(
  () => props.portraitPath,
  () => {
    imgFailed.value = false
  }
)

const avatarSize = computed(() => {
  switch (props.size) {
    case 'small':
      return AVATAR_SIZES.SMALL
    case 'medium':
      return AVATAR_SIZES.MEDIUM
    case 'xlarge':
      return AVATAR_SIZES.XLARGE
    default:
      return AVATAR_SIZES.LARGE
  }
})

const iconSize = computed(() => {
  switch (props.size) {
    case 'small':
      return ICON_SIZES.SMALL
    case 'medium':
      return ICON_SIZES.MEDIUM
    case 'xlarge':
      return ICON_SIZES.XLARGE
    default:
      return ICON_SIZES.LARGE
  }
})
</script>

<template>
  <v-avatar :size="avatarSize" color="rgb(var(--v-theme-authorAvatarBgd))" class="author-avatar">
    <v-img
      v-if="portraitPath && !imgFailed"
      :src="normalizeImagePath(portraitPath)"
      :alt="name"
      cover
      @error="imgFailed = true"
    >
      <template #placeholder>
        <v-icon icon="mdi-account" color="white" :size="iconSize" />
      </template>
    </v-img>
    <v-icon v-else icon="mdi-account" color="white" :size="iconSize" />
  </v-avatar>
</template>
