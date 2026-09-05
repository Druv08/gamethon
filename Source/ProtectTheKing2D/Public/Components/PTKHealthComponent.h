// Protect the King - 2D.
// The one health implementation, shared by every character.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "PTKHealthComponent.generated.h"

class UPTKHealthComponent;

/**
 * Fired whenever health changes, in either direction.
 *
 * `Delta` is signed: negative for damage, positive for healing. Passing it
 * saves every listener from caching the previous value just to work out what
 * happened, which is how hit-reaction and damage-number systems usually end up
 * disagreeing with each other.
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_FourParams(
	FPTKHealthChanged, UPTKHealthComponent*, Component,
	float, NewHealth, float, Delta, AActor*, Instigator);

/** Fired once, on the transition to zero health. */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(
	FPTKDeath, UPTKHealthComponent*, Component, AActor*, Killer);

/**
 * UPTKHealthComponent
 * ===================
 * Health for Ravager, Swarm Node, the King, and everything added later. There
 * is deliberately only one of these: a separate "enemy HP" implementation is
 * how a project ends up with damage that works on one side of the fight and
 * not the other.
 *
 * It hooks AActor::OnTakeAnyDamage, so the engine's own damage path works
 * unchanged:
 *
 *     UGameplayStatics::ApplyDamage(Target, 25.f, Instigator, Causer, nullptr);
 *
 * ApplyDamage() below is the direct entry point and does the same thing without
 * routing through the engine, which is what the melee hit uses.
 *
 * Death fires exactly once. Further damage against a dead actor is ignored
 * rather than re-broadcasting, so a swing that lands on the same frame as a
 * killing blow cannot trigger two death responses.
 */
UCLASS(ClassGroup = (PTK), meta = (BlueprintSpawnableComponent))
class PROTECTTHEKING2D_API UPTKHealthComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UPTKHealthComponent();

	virtual void BeginPlay() override;

	/** Broadcast on every change. Bind in C++ or Blueprint. */
	UPROPERTY(BlueprintAssignable, Category = "PTK|Health")
	FPTKHealthChanged OnHealthChanged;

	/** Broadcast once, when health first reaches zero. */
	UPROPERTY(BlueprintAssignable, Category = "PTK|Health")
	FPTKDeath OnDeath;

	UFUNCTION(BlueprintPure, Category = "PTK|Health")
	float GetMaxHealth() const { return MaxHealth; }

	UFUNCTION(BlueprintPure, Category = "PTK|Health")
	float GetCurrentHealth() const { return CurrentHealth; }

	/** 0..1, safe when MaxHealth is somehow zero. For HP bars. */
	UFUNCTION(BlueprintPure, Category = "PTK|Health")
	float GetHealthFraction() const;

	UFUNCTION(BlueprintPure, Category = "PTK|Health")
	bool IsDead() const { return bDead; }

	/**
	 * Subtracts damage and, if that empties the bar, fires OnDeath once.
	 * Returns the damage actually applied (0 when already dead, or when Amount
	 * was not positive).
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Health")
	float ApplyDamage(float Amount, AActor* DamageInstigator);

	/** Restores health without ever exceeding MaxHealth. Ignored when dead. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Health")
	float Heal(float Amount, AActor* Healer = nullptr);

	/** Refills and clears the dead flag. For respawns and arena resets. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Health")
	void ResetHealth();

	/**
	 * Sets the maximum and refills to it.
	 *
	 * Exists so a character tier can state its own scale in its constructor -
	 * guards are built to absorb a crowd, enemies are not - without every
	 * Blueprint having to remember to override the number.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Health")
	void SetMaxHealth(float NewMax);

protected:
	/**
	 * Prototype balance value. Ravager 100, Swarm Node 70 - set per Blueprint,
	 * never in code, so tuning never needs a recompile.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Health", meta = (ClampMin = "1.0"))
	float MaxHealth = 100.0f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Health")
	float CurrentHealth = 100.0f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Health")
	bool bDead = false;

	/** Bridges the engine damage pipeline into ApplyDamage. */
	UFUNCTION()
	void HandleAnyDamage(AActor* DamagedActor, float Damage,
		const class UDamageType* DamageType, class AController* InstigatedBy,
		AActor* DamageCauser);
};
