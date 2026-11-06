<script setup lang="ts">
import AppShell from './layouts/AppShell.vue'
import {useRoute,RouterView} from 'vue-router'
const route=useRoute()
</script>

<template>
  <RouterView v-if="route.meta.public||route.meta.standalone||route.path==='/auth/change-password'" />
  <AppShell v-else />
</template>
