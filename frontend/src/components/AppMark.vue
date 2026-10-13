<template>
  <div class="mark" aria-hidden="true">
    <span class="mark__bar mark__bar--one" />
    <span class="mark__bar mark__bar--two" />
    <span class="mark__bar mark__bar--three" />
  </div>
</template>

<style scoped>
.mark {
  position: relative;
  width: 2rem;
  height: 2rem;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 0.65rem;
  background: #242629;
}

.mark__bar {
  position: absolute;
  bottom: 0.45rem;
  width: 0.22rem;
  border-radius: var(--radius-pill);
  background: #f2f0ea;
}

.mark__bar--one {
  left: 0.48rem;
  height: 0.52rem;
}

.mark__bar--two {
  left: 0.87rem;
  height: 1rem;
}

.mark__bar--three {
  left: 1.26rem;
  height: 0.76rem;
}
</style>
