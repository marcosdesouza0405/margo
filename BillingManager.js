// BillingManager.js — Google Play Billing via react-native-iap v16
// Uso no App.js:
//   import { useBilling } from './BillingManager';
//   const billing = useBilling(userId, token);
//   billing.buySub('pro_monthly')
//   billing.buySub('pro_plus_monthly')
//   billing.buyExtra()

import { useEffect, useState, useCallback, useRef } from 'react';
import { Alert, Platform } from 'react-native';
import { useIAP, ErrorCode } from 'react-native-iap';

const API_BASE = 'https://margo-production-98a9.up.railway.app';

const SUB_SKUS = ['pro_monthly', 'pro_plus_monthly'];
const PRODUCT_SKUS = ['extra_50'];

export function useBilling(userId, token) {
  const [ready, setReady] = useState(false);
  const subsRef = useRef([]);

  const {
    connected,
    subscriptions,
    products,
    fetchProducts,
    requestPurchase,
    finishTransaction,
  } = useIAP({
    onPurchaseSuccess: async (purchase) => {
      // Guard: evita processar a mesma compra duas vezes
      if (purchase._processed) return;
      purchase._processed = true;
      console.log('[BILLING] Compra recebida:', purchase.productId);

      try {
        const isSub = SUB_SKUS.includes(purchase.productId);

        // Envia pro backend verificar
        const res = await fetch(`${API_BASE}/verificar_compra`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({
            user_id: userId,
            product_id: purchase.productId,
            purchase_token: Platform.OS === 'android' ? purchase.purchaseToken : purchase.transactionReceipt,
            is_subscription: isSub,
            platform: Platform.OS,
          }),
        });

        const data = await res.json();

        if (data.ok) {
          // Finaliza a transação (IMPORTANTE! Senão Google reembolsa em 3 dias)
          await finishTransaction({
            purchase,
            isConsumable: !isSub,
          });
          Alert.alert('Sucesso!', data.message || 'Compra ativada!');
          // Atualiza plano no app
          if (onPlanChange) {
            if (isSub) {
              const plano = purchase.productId === 'pro_plus_monthly' ? 'pro_plus' : 'pro';
              onPlanChange(plano);
            }
          }
        } else {
          Alert.alert('Erro', data.error || 'Não foi possível verificar a compra');
        }
      } catch (err) {
        console.log('[BILLING] Erro ao verificar:', err);
        Alert.alert('Erro', 'Falha ao verificar compra. Tente novamente.');
      }
    },
    onPurchaseError: (error) => {
      if (error.code !== ErrorCode.UserCancelled) {
        console.log('[BILLING] Erro na compra:', error);
        Alert.alert('Erro na compra', error.message || 'Tente novamente');
      }
    },
  });

  // Buscar produtos quando conectar
  useEffect(() => {
    if (connected && !ready) {
      const load = async () => {
        try {
          if (Platform.OS === 'android') {
            await fetchProducts({ skus: SUB_SKUS, type: 'subs' });
            await fetchProducts({ skus: PRODUCT_SKUS, type: 'in-app' });
          } else {
            await fetchProducts({ skus: [...SUB_SKUS, ...PRODUCT_SKUS] });
          }
          setReady(true);
          console.log('[BILLING] Produtos carregados');
        } catch (err) {
          console.log('[BILLING] Erro ao carregar produtos:', err);
        }
      };
      load();
    }
  }, [connected]);

  // Guardar referência das subscriptions pra usar no requestPurchase
  useEffect(() => {
    if (subscriptions && subscriptions.length > 0) {
      subsRef.current = subscriptions;
    }
  }, [subscriptions]);

  // Comprar ou fazer upgrade de assinatura
  const buySub = useCallback(async (sku) => {
    try {
      const sub = subsRef.current.find(s => s.productId === sku || s.id === sku);
      const offerDetails = sub?.subscriptionOfferDetailsAndroid || [];
      const offers = offerDetails.map(offer => ({
        sku: sub.id || sku,
        offerToken: offer.offerToken,
      }));

      if (Platform.OS === 'android') {
        const googleRequest = {
          skus: [sku],
          subscriptionOffers: offers,
        };
        // Verificar se tem assinatura ativa (pra upgrade)
        try {
          const res = await fetch(`${API_BASE}/billing/token/${userId}`);
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
      }
    } catch (err) {
      console.log('[BILLING] Erro ao iniciar compra sub:', err);
    }
  }, [requestPurchase, userId]);

  // Comprar produto consumível (extra_50)
  const buyExtra = useCallback(async () => {
    try {
      if (Platform.OS === 'android') {
        await requestPurchase({
          request: { google: { skus: ['extra_50'] } },
          type: 'in-app',
        });
      } else {
        await requestPurchase({
          request: { apple: { sku: 'extra_50' } },
          type: 'in-app',
        });
      }
    } catch (err) {
      console.log('[BILLING] Erro ao iniciar compra extra:', err);
    }
  }, [requestPurchase]);

  return {
    ready,
    connected,
    subscriptions,
    products,
    buySub,
    buyExtra,
  };
}
