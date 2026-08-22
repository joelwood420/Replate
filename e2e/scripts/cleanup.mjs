// Post-run cleanup: delete the DynamoDB items the e2e demo user created, so e2e runs do not
// pollute real usage metrics. Keyed to the demo user's Cognito sub. Leaves the shared
// restaurant/menu cache and technique corpus alone, keeps the reusable USER#/PROFILE row, and
// lets the RATE#/SCAN and RATE#/RECIPE counters expire on their own TTL. Never fails the job:
// cleanup problems are reported, not fatal.
import {
  CognitoIdentityProviderClient,
  AdminGetUserCommand,
} from '@aws-sdk/client-cognito-identity-provider';
import {
  DynamoDBClient,
  QueryCommand,
  BatchWriteItemCommand,
} from '@aws-sdk/client-dynamodb';

const region = process.env.AWS_REGION || 'ap-southeast-2';
const tableName = process.env.TABLE_NAME;
const userPoolId = process.env.USER_POOL_ID;
const email = process.env.E2E_USER_EMAIL;

if (!tableName || !userPoolId || !email) {
  console.log('cleanup: TABLE_NAME, USER_POOL_ID and E2E_USER_EMAIL are required; skipping.');
  process.exit(0);
}

const ddb = new DynamoDBClient({ region });
const idp = new CognitoIdentityProviderClient({ region });

async function resolveOid() {
  const res = await idp.send(new AdminGetUserCommand({ UserPoolId: userPoolId, Username: email }));
  const sub = res.UserAttributes?.find((a) => a.Name === 'sub')?.Value;
  if (!sub) throw new Error('could not resolve the demo user sub');
  return sub;
}

async function queryPartition(pk, skPrefix) {
  const items = [];
  let ExclusiveStartKey;
  do {
    const res = await ddb.send(
      new QueryCommand({
        TableName: tableName,
        KeyConditionExpression: skPrefix
          ? '#pk = :pk AND begins_with(SK, :sk)'
          : '#pk = :pk',
        ExpressionAttributeNames: { '#pk': 'PK' },
        ExpressionAttributeValues: skPrefix
          ? { ':pk': { S: pk }, ':sk': { S: skPrefix } }
          : { ':pk': { S: pk } },
        ExclusiveStartKey,
      }),
    );
    items.push(...(res.Items ?? []));
    ExclusiveStartKey = res.LastEvaluatedKey;
  } while (ExclusiveStartKey);
  return items;
}

async function batchDelete(items) {
  for (let i = 0; i < items.length; i += 25) {
    const chunk = items.slice(i, i + 25);
    await ddb.send(
      new BatchWriteItemCommand({
        RequestItems: {
          [tableName]: chunk.map((it) => ({
            DeleteRequest: { Key: { PK: it.PK, SK: it.SK } },
          })),
        },
      }),
    );
  }
}

async function main() {
  const oid = await resolveOid();

  // The user's job index rows: USER#<oid> / JOB#<created_at>#<jobId>.
  const indexRows = await queryPartition(`USER#${oid}`, 'JOB#');
  const jobIds = indexRows.map((r) => r.SK.S.split('#').pop()).filter(Boolean);

  let deleted = 0;
  // Each job partition: META / RESULT / ELEMENT# / CANDIDATE# ...
  for (const jobId of jobIds) {
    const jobItems = await queryPartition(`JOB#${jobId}`);
    await batchDelete(jobItems);
    deleted += jobItems.length;
  }
  // Then the index rows themselves.
  await batchDelete(indexRows);
  deleted += indexRows.length;

  console.log(`cleanup: removed ${deleted} item(s) across ${jobIds.length} job(s) for the demo user.`);
}

main().catch((err) => {
  console.error('cleanup failed (non-fatal):', err?.message ?? err);
  process.exit(0);
});
