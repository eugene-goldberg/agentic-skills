import { Context, OpenAIEmbedding, MilvusVectorDatabase } from '@zilliz/claude-context-core';
import fs from 'node:fs';
import path from 'node:path';

const envPath = path.join(process.env.HOME, '.context', '.env');
const envText = fs.readFileSync(envPath, 'utf8');
for (const line of envText.split('\n')) {
  const m = line.match(/^([A-Z_]+)=(.*)$/);
  if (m) process.env[m[1]] = m[2];
}

const REPO = '/Users/eugenegoldberg/dev/ai-projects/agentic-skills/reference-repos/fastapi-good-patterns';

const embedding = new OpenAIEmbedding({
  apiKey: process.env.OPENAI_API_KEY,
  model: process.env.EMBEDDING_MODEL || 'text-embedding-3-small',
});

const vectorDatabase = new MilvusVectorDatabase({
  address: process.env.MILVUS_ADDRESS,
  token: process.env.MILVUS_TOKEN || '',
});

const context = new Context({ embedding, vectorDatabase });

console.log(`Indexing ${REPO} ...`);
const stats = await context.indexCodebase(REPO, (p) => {
  console.log(`  ${p.phase}: ${p.percentage}%`);
});
console.log('Index stats:', JSON.stringify(stats, null, 2));

console.log('\n--- semantic search queries ---');
for (const q of [
  'how to enforce workspace membership before mutating a resource',
  'JWT decode and current user dependency',
  'duplicate-name 409 conflict check on POST endpoint',
]) {
  console.log(`\nQ: ${q}`);
  const results = await context.semanticSearch(REPO, q, 3);
  for (const r of results) {
    const snip = (r.content || '').slice(0, 100).replace(/\n/g, ' ');
    console.log(`  [${r.score?.toFixed(3)}] ${r.relativePath}:L${r.startLine}  ${snip}...`);
  }
}
