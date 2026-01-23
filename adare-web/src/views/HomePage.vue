<template>
  <div class="home-page">
    <div class="hero">
      <h1>ADARE Web Interface</h1>
      <p class="subtitle">
        Build and test playbooks visually with drag-and-drop action builder
      </p>
    </div>

    <div class="container">
      <div class="cards">
        <div class="card">
          <h2>Dev Sessions</h2>
          <p>Start interactive development sessions to build playbooks step-by-step.</p>
          <router-link to="/sessions" class="btn btn-primary">View Sessions</router-link>
        </div>

        <div class="card">
          <h2>Playbook Editor</h2>
          <p>Create and edit playbooks with a visual action sequence builder.</p>
          <router-link to="/playbook/editor" class="btn btn-primary">Open Editor</router-link>
        </div>

        <div class="card">
          <h2>Quick Start</h2>
          <ul>
            <li>Start a new dev session from the Sessions page</li>
            <li>Drag actions from the palette to build your playbook</li>
            <li>Test actions individually with the Test button</li>
            <li>Create checkpoints to save VM state</li>
            <li>Restore checkpoints to undo changes</li>
            <li>Export your playbook to YAML</li>
          </ul>
        </div>
      </div>

      <div class="features">
        <h2>Features</h2>
        <div class="feature-grid">
          <div class="feature">
            <i class="pi pi-th-large"></i>
            <h3>Drag & Drop</h3>
            <p>Visual playbook builder with 18+ action types</p>
          </div>
          <div class="feature">
            <i class="pi pi-bolt"></i>
            <h3>Real-time Testing</h3>
            <p>Execute actions instantly and see results</p>
          </div>
          <div class="feature">
            <i class="pi pi-save"></i>
            <h3>Checkpoints</h3>
            <p>Save and restore VM state at any point</p>
          </div>
          <div class="feature">
            <i class="pi pi-code"></i>
            <h3>YAML Export</h3>
            <p>Export playbooks to YAML format</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.home-page {
  min-height: 100%;
  padding-bottom: 2rem;
}

.hero {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 4rem 2rem;
  text-align: center;
}

.hero h1 {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.subtitle {
  font-size: 1.25rem;
  opacity: 0.9;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
  margin-top: -3rem;
  margin-bottom: 3rem;
}

.card {
  background: white;
  padding: 2rem;
  border-radius: 0.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.card h2 {
  margin-bottom: 0.5rem;
}

.card p {
  color: #64748b;
  margin-bottom: 1rem;
}

.card ul {
  color: #64748b;
  padding-left: 1.5rem;
}

.card li {
  margin-bottom: 0.5rem;
}

.btn {
  display: inline-block;
  padding: 0.5rem 1rem;
  border-radius: 0.25rem;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-primary:hover {
  background: #2563eb;
  text-decoration: none;
}

.features {
  margin-top: 3rem;
}

.features h2 {
  text-align: center;
  margin-bottom: 2rem;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 2rem;
}

.feature {
  text-align: center;
  padding: 1.5rem;
}

.feature i {
  font-size: 2.5rem;
  color: #3b82f6;
  margin-bottom: 1rem;
}

.feature h3 {
  margin-bottom: 0.5rem;
}

.feature p {
  color: #64748b;
}
</style>
