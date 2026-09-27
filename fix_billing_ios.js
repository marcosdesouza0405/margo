const fs = require('fs');
let c = fs.readFileSync('BillingManager.js', 'utf8');

// 1. Adicionar import do Platform
c = c.replace(
  "import { Alert } from 'react-native';",
  "import { Alert, Platform } from 'react-native';"
);

// 2. Corrigir purchaseToken → iOS usa transactionReceipt
c = c.replace(
  `body: JSON.stringify({
            user_id: userId,
            product_id: purchase.productId,
            purchase_token: purchase.purchaseToken,
            is_subscription: isSub,
          }),`,
  `body: JSON.stringify({
            user_id: userId,
            product_id: purchase.productId,
            purchase_token: Platform.OS === 'android' ? purchase.purchaseToken : purchase.transactionReceipt,
            is_subscription: isSub,
            platform: Platform.OS,
          }),`
);

// 3. Corrigir buySub — iOS usa formato diferente
const oldBuySub = `      const googleRequest = {
        skus: [sku],
        subscriptionOffers: offers,
      };

      // Verificar se tem assinatura ativa (pra upgrade)
      try {
        const res = await fetch(\`\${API_BASE}/billing/token/\${userId}\`);
        const data = await res.json();
        if (data.ok && data.purchase_token && data.product_id !== sku) {
          // Upgrade: passa token antigo + modo de cobrança imediata
          googleRequest.purchaseTokenAndroid = data.purchase_token;
          googleRequest.prorationModeAndroid = 1; // IMMEDIATE_CHARGING_FULL_PRICE
          console.log("[BILLING] Upgrade de", data.product_id, "para", sku);
        }
      } catch (e) {
        console.log("[BILLING] Sem token anterior, compra nova");
      }

      await requestPurchase({
        request: { google: googleRequest },
        type: 'subs',
      });`;

const newBuySub = `      if (Platform.OS === 'android') {
        const googleRequest = {
          skus: [sku],
          subscriptionOffers: offers,
        };
        // Verificar se tem assinatura ativa (pra upgrade)
        try {
          const res = await fetch(\`\${API_BASE}/billing/token/\${userId}\`);
          const data = await res.json();
          if (data.ok && data.purchase_token && data.product_id !== sku) {
            googleRequest.purchaseTokenAndroid = data.purchase_token;
            googleRequest.prorationModeAndroid = 1;
            console.log("[BILLING] Upgrade de", data.product_id, "para", sku);
          }
        } catch (e) {
          console.log("[BILLING] Sem token anterior, compra nova");
        }
        await requestPurchase({
          request: { google: googleRequest },
          type: 'subs',
        });
      } else {
        // iOS
        await requestPurchase({
          request: { apple: { sku } },
          type: 'subs',
        });
      }`;

c = c.replace(oldBuySub, newBuySub);

// 4. Corrigir buyExtra — iOS usa formato diferente
const oldExtra = `      await requestPurchase({
        request: {
          google: {
            skus: ['extra_50'],
          },
        },
        type: 'in-app',
      });`;

const newExtra = `      if (Platform.OS === 'android') {
        await requestPurchase({
          request: { google: { skus: ['extra_50'] } },
          type: 'in-app',
        });
      } else {
        await requestPurchase({
          request: { apple: { sku: 'extra_50' } },
          type: 'in-app',
        });
      }`;

c = c.replace(oldExtra, newExtra);

// 5. Corrigir fetchProducts — iOS não precisa de type
const oldFetch = `          await fetchProducts({ skus: SUB_SKUS, type: 'subs' });
          await fetchProducts({ skus: PRODUCT_SKUS, type: 'in-app' });`;

const newFetch = `          if (Platform.OS === 'android') {
            await fetchProducts({ skus: SUB_SKUS, type: 'subs' });
            await fetchProducts({ skus: PRODUCT_SKUS, type: 'in-app' });
          } else {
            await fetchProducts({ skus: [...SUB_SKUS, ...PRODUCT_SKUS] });
          }`;

c = c.replace(oldFetch, newFetch);

fs.writeFileSync('BillingManager.js', c, 'utf8');
console.log('OK - BillingManager atualizado para iOS e Android');
