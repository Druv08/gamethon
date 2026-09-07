// Protect the King - 2D. A guard's base: an objective the enemy can take.

#pragma once

#include "CoreMinimal.h"
#include "Combat/PTKCombatTarget.h"
#include "Core/PTKTypes.h"
#include "GameFramework/Actor.h"
#include "PTKGuardBase.generated.h"

class UCapsuleComponent;
class UPaperSprite;
class UPaperSpriteComponent;
class UPTKHealthComponent;

/**
 * APTKGuardBase
 * =============
 * The platform a guard defends: a static, attackable objective at each of the
 * five posts.
 *
 * Like the King, this derives from AActor and implements IPTKCombatTarget
 * rather than deriving from a Character. A base has no legs, no controller and
 * no animation state - it has a health bar and a position, and making it a
 * Pawn to get those would hand it movement machinery it must never use.
 *
 *
 * A BASE AND ITS GUARD ARE INDEPENDENT
 * ------------------------------------
 * Destroying a base does NOT kill the guard, and killing the guard does NOT
 * destroy the base. They are two separate objectives that happen to share a
 * name and a location. This is deliberate and is the whole reason the enemy
 * targeting question in section 5 is interesting: with the two linked, "attack
 * whichever is closer" would collapse into "attack the guard", because taking
 * one would take the other.
 *
 * The link that does exist is one-directional and informational: GuardId lets
 * the HUD and the minimap show a base beside the guard whose post it is.
 *
 *
 * DESTRUCTION IS TERMINAL, NOT A DELETION
 * ---------------------------------------
 * A destroyed base stays in the world. It stops accepting damage, stops being
 * a valid target, and starts reporting bDestroyed - but the actor remains so
 * the minimap can keep drawing it as lost ground, which is information the
 * player needs. Removing it would silently erase that.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKGuardBase : public AActor, public IPTKCombatTarget
{
	GENERATED_BODY()

public:
	APTKGuardBase();

	// --- IPTKCombatTarget ------------------------------------------
	virtual UPTKHealthComponent* GetCombatHealth() const override { return HealthComponent; }
	virtual EPTKTeam GetCombatTeam() const override { return Team; }
	virtual bool IsCombatDead() const override { return bDestroyed; }

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	UFUNCTION(BlueprintPure, Category = "PTK|Base")
	UPTKHealthComponent* GetHealthComponent() const { return HealthComponent; }

	/** Which guard's post this is, e.g. "Aegis". Informational only. */
	UFUNCTION(BlueprintPure, Category = "PTK|Base")
	FName GetGuardId() const { return GuardId; }

	UFUNCTION(BlueprintPure, Category = "PTK|Base")
	FText GetBaseDisplayName() const { return BaseDisplayName; }

	UFUNCTION(BlueprintPure, Category = "PTK|Base")
	bool IsDestroyed() const { return bDestroyed; }

	/** Seconds since this base last lost health. Large when it is not being hit. */
	UFUNCTION(BlueprintPure, Category = "PTK|Base")
	float GetTimeSinceDamaged() const;

	/** True while this base has taken damage recently enough to warn about. */
	UFUNCTION(BlueprintPure, Category = "PTK|Base")
	bool IsUnderAttack() const;

	UFUNCTION(BlueprintCallable, Category = "PTK|Base|Debug")
	void DebugApplyDamage(float Amount);

protected:
	/** Query-only: enemies walk up to a base, they do not collide with it. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Base")
	TObjectPtr<UCapsuleComponent> Capsule;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Base")
	TObjectPtr<UPTKHealthComponent> HealthComponent;

	/**
	 * Ruins overlay, hidden until the base falls.
	 *
	 * Drawn between the ground and the characters, and cut from the supplied
	 * destroyed-state render at this base's own coordinates - so it lands
	 * exactly on the platform it replaces with no per-base alignment work.
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Base")
	TObjectPtr<UPaperSpriteComponent> RuinsSprite;

	/** Assigned per base by the level builder. Nothing is shown without one. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base")
	TObjectPtr<UPaperSprite> DestroyedSprite;

	/**
	 * Depth of the ruins overlay on the play plane.
	 *
	 * The ground sits at Y=300 and characters depth-sort into roughly
	 * Y=-141..+141, so 250 puts the ruins in front of the map and behind
	 * everything that walks on it.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base")
	float RuinsDepth = 250.0f;

	/** Set per placed base so the HUD can name it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base")
	FName GuardId = NAME_None;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base")
	FText BaseDisplayName;

	/** Prototype value from the spec. Editable per base. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base", meta = (ClampMin = "1.0"))
	float MaxHealth = 2500.0f;

	/** How wide a base reads as a target. Sized to the painted platform. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base", meta = (ClampMin = "1.0"))
	float CollisionRadius = 150.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base", meta = (ClampMin = "1.0"))
	float CollisionHalfHeight = 60.0f;

	/** How long after a hit a base still counts as under attack, for warnings. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Base", meta = (ClampMin = "0.1"))
	float UnderAttackWindow = 3.0f;

	/** Bases are on the guards' side; enemies are hostile to them. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "PTK|Base")
	EPTKTeam Team = EPTKTeam::Guards;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Base")
	bool bDestroyed = false;

	UFUNCTION()
	void HandleHealthChanged(UPTKHealthComponent* Component, float NewHealth,
		float Delta, AActor* DamageInstigator);

	UFUNCTION()
	void HandleDestroyed(UPTKHealthComponent* Component, AActor* Killer);

private:
	/** -1 until the first hit, so an untouched base is never "under attack". */
	float LastDamagedTime = -1.0f;
};
