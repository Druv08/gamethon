// Protect the King - 2D.
// Shared gameplay types for the 2D character system.
//
// These types are deliberately generic: every future character
// (King, Aegis, Wraith, Reaver, Sentinel, Swarm Node, Infiltrator,
// Hijacker, Encrypter, Exfiltrator) reuses them unchanged.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "PTKTypes.generated.h"

class UPaperFlipbook;

/**
 * The four cardinal facing directions used by every PTK 2D character.
 *
 * Never represent a facing direction as a string or a raw int anywhere in
 * the project - always use this enum so the compiler catches typos and so
 * flipbook lookup stays exhaustive.
 */
UENUM(BlueprintType)
enum class EPTKFacingDirection : uint8
{
	Down	UMETA(DisplayName = "Down"),
	Up		UMETA(DisplayName = "Up"),
	Left	UMETA(DisplayName = "Left"),
	Right	UMETA(DisplayName = "Right")
};

/**
 * High level animation state.
 *
 * Attack is a timed state: it is entered by input, holds until its flipbook
 * has played once, and only then hands control back to Idle / Walk. The
 * remaining combat states (Hit / Death) will be appended later - append only,
 * never reorder, so existing Blueprint defaults stay valid.
 */
UENUM(BlueprintType)
enum class EPTKMovementState : uint8
{
	Idle	UMETA(DisplayName = "Idle"),
	Walk	UMETA(DisplayName = "Walk"),
	Attack	UMETA(DisplayName = "Attack")
};

/**
 * One flipbook per cardinal direction.
 *
 * A character supplies one of these per animation state (Idle, Walk, ...).
 * This is what lets a single movement/animation implementation drive every
 * character in the game: the logic never names a specific asset, it only
 * asks a FPTKDirectionalFlipbooks for the flipbook matching a direction.
 */
USTRUCT(BlueprintType)
struct PROTECTTHEKING2D_API FPTKDirectionalFlipbooks
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Flipbooks")
	TObjectPtr<UPaperFlipbook> Down = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Flipbooks")
	TObjectPtr<UPaperFlipbook> Up = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Flipbooks")
	TObjectPtr<UPaperFlipbook> Left = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Flipbooks")
	TObjectPtr<UPaperFlipbook> Right = nullptr;

	/** Returns the flipbook for Direction, or nullptr if that slot is empty. */
	UPaperFlipbook* GetForDirection(EPTKFacingDirection Direction) const;

	/** True when all four directions are assigned. */
	bool IsFullyConfigured() const;

	/** How many of the four slots are assigned (0-4). Used for startup validation logging. */
	int32 NumConfigured() const;
};

/** Blueprint-callable helpers for the types above. */
UCLASS()
class PROTECTTHEKING2D_API UPTKTypesLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Converts a 2D movement input vector into a cardinal facing direction.
	 *
	 * Rule (as specified for PTK): if |X| > |Y| the result is Left/Right,
	 * otherwise it is Up/Down. A perfect 45 degree diagonal therefore
	 * resolves to Up/Down deterministically, which is what keeps keyboard
	 * diagonals from flickering between two animations.
	 *
	 * @param Input             Movement input. +X = right, +Y = up (screen space).
	 * @param CurrentDirection  Direction to keep if Input is inside the dead zone.
	 * @param DeadZone          Input magnitudes at or below this keep CurrentDirection.
	 * @param Hysteresis        Extra margin (0 = exact rule above) the challenging axis
	 *                          must beat before the dominant axis flips. Raise this
	 *                          slightly for analog sticks if 45 degree flicker appears.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Direction")
	static EPTKFacingDirection DirectionFromInput(
		const FVector2D& Input,
		EPTKFacingDirection CurrentDirection,
		float DeadZone = 0.1f,
		float Hysteresis = 0.0f);

	/** Human readable name, for logging and on-screen debug only. */
	UFUNCTION(BlueprintPure, Category = "PTK|Direction")
	static FString DirectionToString(EPTKFacingDirection Direction);
};
