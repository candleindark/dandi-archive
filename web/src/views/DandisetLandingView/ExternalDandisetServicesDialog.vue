<template>
  <v-menu location="left">
    <template #activator="{ props }">
      <v-btn
        id="external-dandiset-services"
        variant="outlined"
        block
        class="justify-space-between"
        v-bind="props"
      >
        <template #prepend>
          <v-icon
            color="primary"
            start
          >
            mdi-web
          </v-icon>
          <span>Open with</span>
        </template>
        <template #append>
          <v-icon end>
            mdi-chevron-down
          </v-icon>
        </template>
      </v-btn>
    </template>
    <v-card>
      <v-list>
        <v-tooltip
          open-on-hover
          location="left"
        >
          <template #activator="{ props }">
            <div v-bind="props">
              <v-list-item
                :href="neurosiftURL"
                target="_blank"
              >
                <v-icon
                  color="primary"
                  start
                  size="small"
                >
                  mdi-web
                </v-icon>
                Neurosift
              </v-list-item>
            </div>
          </template>
          <span>Open the Dandiset in Neurosift</span>
        </v-tooltip>
      </v-list>
    </v-card>
  </v-menu>
</template>
<script setup lang="ts">
import { computed } from 'vue';
import { useDandisetStore } from '@/stores/dandiset';

const store = useDandisetStore();

const currentDandiset = computed(() => store.dandiset);

const neurosiftURL = computed(() => {
  if (!currentDandiset.value) {
    throw new Error('Dandiset is undefined');
  }

  if (!currentDandiset.value.metadata) {
    throw new Error('Dandiset metadata is undefined');
  }

  if (!currentDandiset.value.metadata.url) {
    throw new Error('Dandiset metadata.url is undefined');
  }

  const metadata = currentDandiset.value.metadata;
  const dandisetId = currentDandiset.value.dandiset.identifier;
  const dandisetVersion = metadata.version;
  const stagingParam = metadata.url!.startsWith('https://sandbox.dandiarchive.org/') ? '&staging=1' : '';

  return `https://neurosift.app/dandiset/${dandisetId}?dandisetVersion=${dandisetVersion}${stagingParam}`;
});

</script>
