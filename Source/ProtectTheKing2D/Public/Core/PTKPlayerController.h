// Protect the King - 2D. The player controller, and the only thing that decides
// which guard the player is driving.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "PTKPlayerController.generated.h"

class APTKGuardAIController;
class APTKGuardCharacter;
class UInputAction;
class UInputMappingContext;
class UPTKHealthComponent;

/**
 * APTKPlayerController
 * ====================
 * Holds the guard roster and moves the player between guards.
 *
 *     1  Ravager      2  Aegis      3  Wraith      4  Reaver      5  Sentinel
 *
 * Exactly one living guard is player-driven and every other living guard is
 * AI-driven, at every instant. That is not maintained by bookkeeping here - it
 * is structural. A pawn in Unreal has exactly ONE controller, so possessing a
 * guard detaches whatever held it, and the two states cannot overlap even for a
 * frame. All this class has to do is make sure the guard the player LEFT gets a
 * controller back, which is the whole of ReleaseToAI().
 *
 *
 * WHY THE SWITCH KEYS LIVE ON THE CONTROLLER AND NOT ON THE PAWN
 * -------------------------------------------------------------
 * The pawn is the thing being swapped. Binding the number keys to it would mean
 * the binding is destroyed and rebuilt on every switch, that every guard
 * Blueprint has to carry the roster, and that a guard with a missing input
 * asset - which has happened once already in this project - would be a guard the
 * player could enter and never leave.
 *
 * The controller survives possession changes, so its bindings are set up once at
 * startup and are alive before the first pawn exists and after the last one
 * dies. IA_Move / IA_Attack / IA_Defend are untouched: they stay on the pawn,
 * bound by APTKTopDownCharacter::SetupPlayerInputComponent exactly as before, so
 * a guard the player takes over gets its OWN abilities with no extra wiring -
 * Aegis's shield, Wraith's bow and Sentinel's splash all arrive with the pawn.
 *
 * The switch keys are also in their own mapping context (IMC_PTK_GuardSwitch),
 * added by this controller rather than by the pawn, for the same reason.
 *
 *
 * WHAT SURVIVES A SWITCH
 * ----------------------
 * Health, movement state, facing, attack cooldowns, stats and HomePosition all
 * live on the CHARACTER, so they survive by construction - nothing is copied,
 * saved or restored anywhere in this file. The one piece of state that lives on
 * an AI controller is its defend cooldown, which is why a guard's AI controller
 * is parked and re-used rather than destroyed and replaced: a guard handed back
 * to the AI resumes with the cooldown it had, instead of being able to block
 * again instantly by being switched away from and back.
 *
 * HomePosition in particular is never rewritten here. A guard returns to the
 * post it was placed on, not to wherever the player abandoned it.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	APTKPlayerController();

	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	virtual void OnPossess(APawn* InPawn) override;
	virtual void OnUnPossess() override;

	/**
	 * Moves the player to the guard in a 1-based slot.
	 *
	 * Refused - with a log line and no side effects - when the slot is empty,
	 * when that guard is dead, or when the player is already driving it.
	 * Returns true only if control actually moved.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Guard|Switch")
	bool SelectGuardSlot(int32 Slot);

	/** The guard in a slot whether it is alive or dead, or null if absent. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|Switch")
	APTKGuardCharacter* GetGuardInSlot(int32 Slot) const;

	/** 1-based slot of a guard, or INDEX_NONE. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|Switch")
	int32 GetSlotOf(const APTKGuardCharacter* Guard) const;

	/** The guard the player is driving right now, or null. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|Switch")
	APTKGuardCharacter* GetPlayerGuard() const;

	/** Roster order: the number keys, and the order death hands control on. */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|Switch")
	const TArray<FName>& GetGuardOrder() const { return GuardOrder; }

	/**
	 * Next living guard at or after the slot following AfterSlot, wrapping once.
	 * INDEX_NONE when the whole line is down. Pass INDEX_NONE to start at slot 1.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Guard|Switch")
	int32 FindNextLivingSlot(int32 AfterSlot) const;

	/** Logs slot / health / controller for every guard. Verification aid. */
	void LogRoster(const FString& Stage) const;

protected:
	/**
	 * Possesses a guard and hands the previous one back to the AI.
	 *
	 * The only path control ever moves along - the number keys, the death
	 * hand-off and the console command all end up here, so there is one
	 * ordering to get right rather than three.
	 */
	bool TakeControlOf(APTKGuardCharacter* Guard);

	/**
	 * Gives a guard back to the guard AI: its parked controller if it still
	 * exists, otherwise a fresh one from the Blueprint's AIControllerClass.
	 */
	void ReleaseToAI(APTKGuardCharacter* Guard);

	/** Registers IMC_PTK_GuardSwitch with the Enhanced Input subsystem. */
	void AddSwitchMappingContext();

	/** Bound with the slot number as payload - see SetupInputComponent. */
	void Input_SelectGuard(int32 Slot);

	UFUNCTION()
	void HandlePlayerGuardDeath(UPTKHealthComponent* Component, AActor* Killer);

	/** Deferred body of the death hand-off. See HandlePlayerGuardDeath. */
	void AutoSwitchAfterDeath(int32 FallenSlot);

	/**
	 * Roster order. Slot N is GuardOrder[N-1], matched against GuardId.
	 *
	 * Matched by id rather than by class or by placement order so the numbers
	 * mean the same thing however the level was built - Ravager is spawned by
	 * the game mode and the other four are placed in the map, and neither the
	 * spawn order nor the actor order in the level is something the player
	 * should be able to feel.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Guard|Switch")
	TArray<FName> GuardOrder;

	/** IMC_PTK_GuardSwitch. Separate from IMC_PTK_Default, which is the pawn's. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Input")
	TObjectPtr<UInputMappingContext> SwitchMappingContext;

	/**
	 * IA_SelectGuard1..5, in slot order.
	 *
	 * Five digital actions rather than one action with five keys, because
	 * Enhanced Input hands a delegate the action's VALUE and never the key that
	 * produced it - so a single action could not tell 2 from 4.
	 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Input")
	TArray<TObjectPtr<UInputAction>> GuardSelectActions;

	/** Above the pawn's context, though the two share no keys. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Input")
	int32 SwitchMappingPriority = 1;

private:
	/**
	 * GuardId -> the AI controller that was driving it when the player took over.
	 *
	 * Keyed by id, not by actor pointer, so a destroyed guard cannot be kept
	 * alive by this map. Re-using the controller is what preserves the AI's
	 * defend cooldown across a switch.
	 */
	UPROPERTY()
	TMap<FName, TObjectPtr<APTKGuardAIController>> ParkedAI;
};
